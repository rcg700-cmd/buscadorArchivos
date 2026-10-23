"""Escaneo del disco para encontrar archivos de Office (y PDF).

Busca SOLO por nombre/metadatos: recorre el sistema de archivos de forma
iterativa (con una pila, para no agotar la recursión), comprueba extensiones y
lee nombre, tipo, fechas y tamaño. No abre ni parsea los documentos.
"""

import fnmatch
import hashlib
import json
import os
import queue
import string
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Hilos en paralelo: escanear carpetas distintas a la vez (cuello de botella = I/O de disco)
N_HILOS = max(4, min(32, (os.cpu_count() or 4) * 4))

# Extensiones admitidas -> nombre amigable del tipo
EXTENSIONES = {
    ".doc": "Word",
    ".docx": "Word",
    ".docm": "Word",
    ".xls": "Excel",
    ".xlsx": "Excel",
    ".xlsm": "Excel",
    ".ppt": "PowerPoint",
    ".pptx": "PowerPoint",
    ".pptm": "PowerPoint",
    ".pdf": "PDF",
    ".odt": "LibreOffice",
    ".ods": "LibreOffice",
    ".odp": "LibreOffice",
}

# Carpetas del sistema que no vale la pena recorrer
CARPETAS_IGNORADAS = {
    "$recycle.bin",
    "system volume information",
    "proc",
    "sys",
    "dev",
    "run",
}


@dataclass
class Registro:
    """Un archivo de Office encontrado en el disco."""

    ruta: str
    nombre: str
    tipo: str
    tamano: int
    creado: datetime
    modificado: datetime
    nombre_min: str  # nombre en minúsculas para filtrar rápido


def raices_por_defecto():
    """Raíces de búsqueda: todos los discos en Windows, todo "/" en Linux."""
    if os.name == "nt":
        return [f"{letra}:\\" for letra in string.ascii_uppercase if os.path.exists(f"{letra}:\\")]
    return ["/"]


def escanear(raices, salida, guardar=True):
    """Escanea las raíces en paralelo (varios hilos) y mete cada archivo
    encontrado en la cola `salida` conforme llega.

    Al terminar enfila la tupla ("fin", lista_completa) —la lista fresca
    completa— y, si `guardar` es verdadero, la guarda en la caché. Los errores
    de permisos o de carpetas inaccesibles se ignoran silenciosamente.

    Coordinación: `pendientes` cuenta las carpetas descubiertas que aún
    nadie procesó (se incrementa antes de encolarlas y se decrementa al
    terminar de procesarlas). Cuando llega a 0 ya no queda nada en cola ni
    en vuelo, y los trabajadores se retiran.
    """
    pendientes = [len(raices)]  # lista mutable compartida entre hilos
    lock = threading.Lock()
    parado = threading.Event()
    cola_dirs = queue.Queue()
    cola_salida = queue.Queue()  # registros frescos: trabajadores → coordinator
    patrones_excluir = _cargar_exclusiones()  # de excluir.txt (una lectura por escaneo)
    for raiz in raices:
        cola_dirs.put(raiz)

    def trabajador():
        while not parado.is_set():
            try:
                carpeta = cola_dirs.get(timeout=0.05)
            except queue.Empty:
                with lock:
                    if pendientes[0] <= 0:
                        return
                continue
            try:
                with os.scandir(carpeta) as entradas:
                    for entrada in entradas:
                        try:
                            if entrada.is_dir(follow_symlinks=False):
                                # Salta enlaces y carpetas del sistema
                                if entrada.is_symlink():
                                    continue
                                if entrada.name.lower() in CARPETAS_IGNORADAS:
                                    continue
                                nueva = entrada.path
                                if _carpeta_excluida(nueva, patrones_excluir):
                                    continue
                                with lock:
                                    pendientes[0] += 1
                                cola_dirs.put(nueva)
                            else:
                                ext = os.path.splitext(entrada.name)[1].lower()
                                if ext not in EXTENSIONES:
                                    continue
                                st = entrada.stat()
                                nombre = entrada.name
                                cola_salida.put(
                                    Registro(
                                        ruta=entrada.path,
                                        nombre=nombre,
                                        tipo=EXTENSIONES[ext],
                                        tamano=st.st_size,
                                        creado=datetime.fromtimestamp(st.st_ctime),
                                        modificado=datetime.fromtimestamp(st.st_mtime),
                                        nombre_min=nombre.casefold(),
                                    )
                                )
                        except (OSError, OverflowError, ValueError):
                            # stat/fecha ilegibles para ese archivo: se salta
                            # (un OverflowError aquí mataría al trabajador
                            # entero y dejaría el escaneo parcial)
                            continue
            except OSError:
                pass
            finally:
                with lock:
                    pendientes[0] -= 1

    hilos = [threading.Thread(target=trabajador, daemon=True) for _ in range(N_HILOS)]
    encontrados = []
    for h in hilos:
        h.start()
    while any(h.is_alive() for h in hilos):
        # Traslada lo fresco a la salida para que la UI lo muestre al vuelo
        try:
            while True:
                encontrados.append(cola_salida.get_nowait())
                salida.put(encontrados[-1])
        except queue.Empty:
            pass
        with lock:
            cola_pend = pendientes[0]
        salida.put(("progreso", len(encontrados), max(0, cola_pend)))
        parado.wait(0.1)
    # Recolecta lo que quede antes de anunciar el fin
    while True:
        try:
            encontrados.append(cola_salida.get_nowait())
            salida.put(encontrados[-1])
        except queue.Empty:
            break
    salida.put(("fin", encontrados))
    if guardar:
        guardar_cache(tuple(raices), encontrados)


def validar_cache(registros):
    """Validación incremental: descarta entradas cuyo archivo ya no existe.

    Devuelve (lista_viva, n_expiradas) conservando el orden de entrada. Solo
    comprueba la existencia (una llamada ligera a exists(); no re-escanea ni
    detecta archivos nuevos — para eso está F5).
    """
    vivas = [r for r in registros if os.path.exists(r.ruta)]
    return vivas, len(registros) - len(vivas)


def borrar_cache():
    """Borra TODAS las cachés (cualquier ámbito). Devuelve True si borro algo."""
    borrado = False
    try:
        archivos = list(_carpeta_cache().glob("cache*.json"))
    except OSError:
        return False
    for p in archivos:
        try:
            p.unlink()
            borrado = True
        except OSError:
            pass
    return borrado


PLANTILLA_EXCLUIR = """\
# excluir.txt — carpetas que el buscador ignora durante el escaneo.
# Cada línea no comentada es un fragmento de la ruta de una carpeta a
# ignorar (insensible a mayúsculas); admite comodines * y ?.
# Ejemplos:
#   node_modules
#   C:\\Users\\*\\AppData\\Local\\Packages
"""


def _cargar_exclusiones():
    """Lee (o crea con su plantilla) excluir.txt junto a las cachés.

    Devuelve una tupla de ('sub', texto) o ('glob', patron) en minúsculas.
    """
    ruta = _carpeta_cache() / "excluir.txt"
    try:
        if not ruta.exists():
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_text(PLANTILLA_EXCLUIR, encoding="utf-8")
        lineas = ruta.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return ()
    patrones = []
    for linea in lineas:
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        clave = linea.casefold()
        if "*" in clave or "?" in clave:
            patrones.append(("glob", clave))
        else:
            patrones.append(("sub", clave))
    return tuple(patrones)


def _carpeta_excluida(ruta, patrones):
    """True si la carpeta casa con alguna exclusión (subcadena o patrón).

    Se prueba la ruta tal cual y también con barra final, para que un
    patrón como ``*\\Docs\\`` excluya tanto a la carpeta Docs como a
    todo lo que cuelga de ella.
    """
    r = ruta.casefold()
    r2 = r + os.sep
    for tipo, patron in patrones:
        if tipo == "sub":
            if patron in r or patron in r2:
                return True
        elif fnmatch.fnmatch(r, patron) or fnmatch.fnmatch(r2, patron):
            return True
    return False


def iniciar_escaneo(raices, guardar=True):
    """Devuelve (hilo, cola). Llamar a hilo.start() para comenzar."""
    cola = queue.Queue()
    hilo = threading.Thread(target=escanear, args=(tuple(raices), cola), kwargs={"guardar": guardar}, daemon=True)
    return hilo, cola


# --------------------------------------------------------------------- caché


def _carpeta_cache() -> Path:
    """Carpeta donde viven los archivos de caché (perfil de usuario, fuera del repo)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(base) / "buscador-archivo"


def _ruta_cache(raices):
    """Ruta de la caché para un ámbito concreto (cada raíces tiene su archivo,
    así alternar entre 'todo el disco' y una carpeta no re-escanea cada vez)."""
    clave = hashlib.sha1(repr(tuple(raices)).encode("utf-8")).hexdigest()[:8]
    return _carpeta_cache() / f"cache_{clave}.json"


def guardar_cache(raices, registros):
    """Guarda la lista completa de registros (atómica: escribe a .tmp y reemplaza)."""
    ruta = _ruta_cache(raices)
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = {
            "version": 1,
            "raices": list(raices),
            "registros": [
                {
                    "ruta": r.ruta,
                    "nombre": r.nombre,
                    "tipo": r.tipo,
                    "tamano": r.tamano,
                    "creado": r.creado.isoformat(),
                    "modificado": r.modificado.isoformat(),
                    "nombre_min": r.nombre_min,
                }
                for r in registros
            ],
        }
        tmp = ruta.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(datos, separators=(",", ":")), encoding="utf-8")
        tmp.replace(ruta)
    except OSError:
        pass  # la caché es un extra: si falla, no interfiere


def cargar_cache(raices):
    """Devuelve la lista de registros de la caché, o None si no es válida.

    Solo acepta cachés cuya lista de raíces coincida exactamente con las de
    esta ejecución (un escaneo con otras raíces no sirve).
    """
    ruta = _ruta_cache(raices)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Limpieza silenciosa de la caché antigua de un solo archivo (pre v1.0)
        legada = _carpeta_cache() / "cache.json"
        if legada.exists():
            try:
                legada.unlink()
            except OSError:
                pass
        return None
    if datos.get("version") != 1 or datos.get("raices") != list(raices):
        return None
    registros = []
    for d in datos.get("registros", []):
        try:
            registros.append(
                Registro(
                    ruta=d["ruta"],
                    nombre=d["nombre"],
                    tipo=d["tipo"],
                    tamano=d["tamano"],
                    creado=datetime.fromisoformat(d["creado"]),
                    modificado=datetime.fromisoformat(d["modificado"]),
                    nombre_min=d["nombre_min"],
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return registros
