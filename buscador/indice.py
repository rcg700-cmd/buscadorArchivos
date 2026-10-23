"""indice: índice SQLite del contenido de los documentos.

Capa de almacenamiento ( hilos y pool van en `pasada_indice`): esquema,
guardado por documento (texto normalizado para LIKE + blob zlib para el
fragmento), búsqueda por coincidencias con comodines y saneo de rutas
que ya no existen. Un archivo de índice por ámbito, con la misma clave
SHA1 que la caché de registros.
"""

import hashlib
import sqlite3
import zlib

from .escaner import _carpeta_cache
from .texto import normalizar

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
    """Conexión con el esquema en su sitio; la carpeta de caché ya existe."""
    bd = sqlite3.connect(ruta)
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
