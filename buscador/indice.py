"""indice: índice SQLite del contenido de los documentos.

Capa de almacenamiento ( hilos y pool van en `pasada_indice`): esquema,
guardado por documento (texto normalizado para LIKE + blob zlib para el
fragmento), búsqueda por coincidencias con comodines y saneo de rutas
que ya no existen. Un archivo de índice por ámbito, con la misma clave
SHA1 que la caché de registros.
"""

import hashlib
import os
import queue
import sqlite3
import threading
import time
import zlib

from . import texto
from .escaner import N_HILOS, _carpeta_cache
from .texto import extraer_texto, normalizar

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS docs (
  ruta        TEXT PRIMARY KEY,
  mtime       REAL,
  tamano      INTEGER,
  texto_norm  TEXT,
  texto_blob  BLOB
);
CREATE TABLE IF NOT EXISTS meta (
  clave  TEXT PRIMARY KEY,
  valor  TEXT
);
"""


def ruta_indice(raices):
    """Archivo del índice para un ámbito (misma clave de 8 que `_ruta_cache`)."""
    clave = hashlib.sha1(repr(tuple(raices)).encode("utf-8")).hexdigest()[:8]
    return _carpeta_cache() / f"indice_{clave}.db"


def abrir_bd(ruta):
    """Conexión con el esquema en su sitio; la carpeta de caché ya existe.

    `check_same_thread=False`: la creada en un hilo, la usa el escritor en
    otro; todas las guardas van en serie por ese único hilo, con su lock.
    """
    bd = sqlite3.connect(ruta, check_same_thread=False)
    bd.executescript(_ESQUEMA)
    bd.execute("INSERT OR REPLACE INTO meta(clave, valor) VALUES('version', '1')")
    bd.commit()
    return bd


def existe_actualizada(bd, ruta, mtime, tamano):
    """¿Hay fila del documento y coincide mtime/peso con los vigentes?"""
    fila = bd.execute(
        "SELECT mtime, tamano FROM docs WHERE ruta=?", (ruta,)
    ).fetchone()
    return bool(fila) and fila[0] == mtime and fila[1] == tamano


def guardar_doc(bd, ruta, mtime, tamano, texto):
    """Fila del documento, texto normalizado para buscar y blob para fragmentar.

    Solo ejecuta la sentencia; el `commit` lo hace el llamador (las tandas).
    """
    bd.execute(
        "INSERT OR REPLACE INTO docs(ruta, mtime, tamano, texto_norm, texto_blob)"
        " VALUES(?,?,?,?,?)",
        (ruta, mtime, tamano, normalizar(texto), zlib.compress(texto.encode("utf-8"))),
    )


def texto_de(bd, ruta):
    """Texto original (sin normalizar) del documento; `""` ante cualquier fallo."""
    try:
        fila = bd.execute(
            "SELECT texto_blob FROM docs WHERE ruta=?", (ruta,)
        ).fetchone()
        if fila is None:
            return ""
        return zlib.decompress(fila[0]).decode("utf-8")
    except (sqlite3.Error, zlib.error, UnicodeDecodeError):
        return ""


def patron_sql(texto):
    """Consulta del usuario -> patrón LIKE: escapa literales y traduce comodines.

    El orden importa: `\\`, `%` y `_` literales se protegen ANTES de convertir
    `*`->`%` y `?`->`_`; si se tradujera primero, los comodines recién puestos
    quedarían escapados también.
    """
    escapado = texto.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return escapado.replace("*", "%").replace("?", "_")


def buscar_ph(bd, texto, limite=5000):
    """Rutas cuyo texto normalizado contiene la frase (con `*`?`;` comodines)."""
    patron = "%" + patron_sql(texto) + "%"
    filas = bd.execute(
        "SELECT ruta FROM docs WHERE texto_norm LIKE ? ESCAPE '\\' LIMIT ?",
        (patron, limite),
    ).fetchall()
    return [fila[0] for fila in filas]


def limpiar_bd(bd, rutas_validas):
    """Borra filas de rutas fuera del ámbito (archivos ya no vistos). Devuelve cuántas."""
    try:
        filas = bd.execute("SELECT ruta FROM docs").fetchall()
        sobran = [fila[0] for fila in filas if fila[0] not in rutas_validas]
        if sobran:
            bd.executemany("DELETE FROM docs WHERE ruta=?", ((r,) for r in sobran))
            bd.commit()
        return len(sobran)
    except sqlite3.Error:
        return 0


# ------------------------------------------------ pasada de índice (pool)

# Hilos dedicados a extraer texto: extraer es CPU+disco, con menos de lo
# que gasta el escaneo de carpetas basta (los documentos suelen ser menos).
N_HILOS_INDICE = max(2, min(8, N_HILOS))


def pasada_indice(raices, registros, cola, gen, cancelar):
    """Indexa el contenido faltante de los registros. BLOQUEANTE: lláncz
    dentro de un `threading.Thread(daemon=True)`.

    Crea su propio pool de extracción y un hilo escritor que serializa las
    guardas en la BD. Sobre `cola` publica:
      - ("indice", gen, raices, hechos, total, sin_texto) cada ~1 s y
      - ("indice_fin", gen, raices) al terminar (también al cancelar, sin progreso).
    Al acabar sanea el índice con lo pendiente del ámbito.
    """
    try:
        if cancelar.is_set():
            return
        _pasada_interna(raices, registros, cola, gen, cancelar)
    finally:
        # El fin SIEMPRE sale, aunque reviente algo: la app no se queda colgada.
        cola.put(("indice_fin", gen, raices))


def _pasada_interna(raices, registros, cola, gen, cancelar):
    bd = abrir_bd(ruta_indice(raices))
    extraibles = texto.EXTRACCION | {".pdf"}
    pendientes = []
    for r in registros:
        if cancelar.is_set():
            bd.close()
            return
        ext = os.path.splitext(r.ruta)[1].lower()
        if ext not in extraibles:
            continue
        try:
            st = os.stat(r.ruta)
        except OSError:
            continue
        if st.st_size > texto.MAX_TAMANO_ARCHIVO:
            continue
        if existe_actualizada(bd, r.ruta, st.st_mtime, st.st_size):
            continue
        pendientes.append((r.ruta, st.st_mtime, st.st_size))

    total = len(pendientes)
    progreso = {"hechos": 0, "sin_texto": 0}
    if pendientes:
        _indexar(bd, pendientes, total, progreso, raices, gen, cola, cancelar)

    if cancelar.is_set():
        # Al cancelar se cierra y se sale: sin progreso y sin saneo.
        bd.close()
        return
    cola.put(("indice", gen, raices, progreso["hechos"], total, progreso["sin_texto"]))
    limpiar_bd(bd, {r.ruta for r in registros})
    bd.close()


def _indexar(bd, pendientes, total, progreso, raices, gen, cola, cancelar):
    """Pool de extracción + escritor serial; progreso cada segundo."""
    cola_texto = queue.Queue()
    siguiente = [0]
    candado = threading.Lock()

    def trabajador():
        while not cancelar.is_set():
            with candado:
                i = siguiente[0]
                if i >= len(pendientes):
                    return
                siguiente[0] = i + 1
            ruta, mtime, tamano = pendientes[i]
            texto_doc = extraer_texto(ruta)
            cola_texto.put((ruta, mtime, tamano, texto_doc))

    def escritor():
        hechos = sin_texto = 0
        while True:
            try:
                item = cola_texto.get(timeout=0.05)
            except queue.Empty:
                continue
            if item is None:
                break
            try:
                ruta, mtime, tamano, texto_doc = item
                if texto_doc is not None:
                    guardar_doc(bd, ruta, mtime, tamano, texto_doc)
                else:
                    sin_texto += 1
                hechos += 1
                progreso["hechos"] = hechos
                progreso["sin_texto"] = sin_texto
            except sqlite3.Error:
                # fila ilegible: se salta, la pasada sigue
                pass
            finally:
                cola_texto.task_done()
        bd.commit()

    hilos = [
        threading.Thread(target=trabajador, daemon=True) for _ in range(N_HILOS_INDICE)
    ]
    pluma = threading.Thread(target=escritor, daemon=True)
    for hilo in hilos:
        hilo.start()
    pluma.start()

    proximo = time.monotonic() + 1.0
    while any(hilo.is_alive() for hilo in hilos):
        if time.monotonic() >= proximo:
            proximo = time.monotonic() + 1.0
            cola.put(
                ("indice", gen, raices, progreso["hechos"], total, progreso["sin_texto"])
            )
        time.sleep(0.05)
    # Los extractores acabaron; se espera a que el escritor drene TODO lo
    # encolado (join de la cola de texto) y recién entonces se le corta.
    cola_texto.join()
    cola_texto.put(None)
    pluma.join()
