"""Escaneo del disco para encontrar archivos de Office (y PDF).

Busca SOLO por nombre/metadatos: recorre el sistema de archivos de forma
iterativa (con una pila, para no agotar la recursión), comprueba extensiones y
lee nombre, tipo, fechas y tamaño. No abre ni parsea los documentos.
"""

import json
import os
import queue
import string
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

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


def escanear(raices, cola, guardar=True):
    """Recorre las raíces y mete cada archivo encontrado en la cola.

    Al terminar enfila la tupla ("fin", lista_completa) —la lista fresca
    completa— y, si `guardar` es verdadero, la guarda en la caché. Los errores
    de permisos o de carpetas inaccesibles se ignoran silenciosamente.
    """
    encontrados = []
    for raiz in raices:
        pila = [raiz]
        while pila:
            carpeta = pila.pop()
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
                                pila.append(entrada.path)
                            else:
                                ext = os.path.splitext(entrada.name)[1].lower()
                                if ext not in EXTENSIONES:
                                    continue
                                st = entrada.stat()
                                nombre = entrada.name
                                r = Registro(
                                    ruta=entrada.path,
                                    nombre=nombre,
                                    tipo=EXTENSIONES[ext],
                                    tamano=st.st_size,
                                    creado=datetime.fromtimestamp(st.st_ctime),
                                    modificado=datetime.fromtimestamp(st.st_mtime),
                                    nombre_min=nombre.casefold(),
                                )
                                encontrados.append(r)
                                cola.put(r)
                        except OSError:
                            continue
            except OSError:
                continue
    cola.put(("fin", encontrados))
    if guardar:
        guardar_cache(tuple(raices), encontrados)


def iniciar_escaneo(raices, guardar=True):
    """Devuelve (hilo, cola). Llamar a hilo.start() para comenzar."""
    cola = queue.Queue()
    hilo = threading.Thread(target=escanear, args=(tuple(raices), cola), kwargs={"guardar": guardar}, daemon=True)
    return hilo, cola


# --------------------------------------------------------------------- caché


def _ruta_cache() -> Path:
    """Ruta del archivo de caché según el sistema operativo (fuera del repo)."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(base) / "buscador-archivo" / "cache.json"


def guardar_cache(raices, registros):
    """Guarda la lista completa de registros (atómica: escribe a .tmp y reemplaza)."""
    ruta = _ruta_cache()
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
    try:
        datos = json.loads(_ruta_cache().read_text(encoding="utf-8"))
    except (OSError, ValueError):
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
