"""Texto: normalización (buscar sin tildes, 1:1) y extracción de contenido.

`normalizar` es la base del filtrado por nombre y del índice de contenido:
ambas búsquedas deben responder igual escriba el usuario con o sin acentos.
Garantía clave: la salida SIEMPRE mide lo mismo que la entrada (por eso no
se usa ni str.casefold() — 'ß'.casefold() == 'ss' — ni una descomposición
NFD recortada, que cambia larguras).
"""

import os
import re
import zipfile
import xml.etree.ElementTree as ET

import unicodedata


def _construir_tabla():
    """Tabla de traducción 1:1: cada carácter con tilde -> su base en minúscula.

    Se deriva de las descomposiciones Unicode (ASCII a U+0x300) para cubrir
    áéíóú, äå, etc. sin una lista a mano; solo entra un mapeo si el resultado
    es exactamente un carácter (nunca cambia la longitud).
    """
    tabla = {}
    for cp in range(32, 0x300):
        c = chr(cp)
        d = unicodedata.normalize("NFD", c)
        base = "".join(ch for ch in d if unicodedata.category(ch) != "Mn").lower()
        if len(base) == 1 and base != c:
            tabla[cp] = base
    return tabla


_TABLA = _construir_tabla()


def fragmento(texto: str, termino: str, ventana: int = 120) -> str:
    """Trozo del texto original centrado en la primera aparición del término.

    Se busca sobre una copia normalizada; como `normalizar` es 1:1, el índice
    sirve para el original (aquí el término puede aparecer en MAYÚSCULAS o con
    tildes y aun así se encuentra). Devuelve '…' + hasta `ventana` caracteres
    (~30 de contexto antes del hit) con el hit DENTRO; `""` sin texto o sin hit.
    """
    if not texto or not termino:
        return ""
    copia = normalizar(texto)
    pos = copia.find(normalizar(termino))
    if pos < 0:
        return ""
    desde = max(0, pos - 30)
    hasta = min(len(texto), desde + ventana)
    pref = "…" if desde > 0 else ""
    suf = "…" if hasta < len(texto) else ""
    return f"{pref}{texto[desde:hasta].strip()}{suf}"


def normalizar(texto: str) -> str:
    """Minúsculas por carácter + tildes a la base; la longitud no cambia."""
    if not isinstance(texto, str):
        raise TypeError("normalizar espera un str")
    return texto.translate(_TABLA)


# ---------------------------------------------------------------- extracción

# Formatos OOXML/ODF que llevan su contenido en un ZIP de XML internos.
EXTRACCION = {".docx", ".docm", ".pptx", ".pptm", ".xlsx", ".xlsm", ".odt", ".ods", ".odp"}

# PDF: tope de peso por archivo y de páginas leídas (los ultralargos se
# indexan parcialmente, según el diseño aprobado).
MAX_TAMANO_ARCHIVO = 100 * 1024 * 1024
MAX_PAGINAS_PDF = 500

_SLIDE_AION = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_HOJA_AION = re.compile(r"^xl/worksheets/sheet\d+\.xml$")


def extraer_texto(ruta: str):
    """Devuelve el texto legible del documento, o None si no se puede extraer.

    Devuelve None para los formatos viejos (.doc/.xls/.ppt: se buscan solo
    por nombre, según el diseño) y para cualquier archivo dañado o ilegible.
    Nunca lanza: los documentos del disco están fuera de nuestro control.
    """
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in EXTRACCION and ext != ".pdf":
        return None
    try:
        if ext == ".pdf":
            if os.path.getsize(ruta) > MAX_TAMANO_ARCHIVO:
                return None
            return _texto_pdf(ruta)
        with zipfile.ZipFile(ruta) as z:
            if ext in (".docx", ".docm"):
                return _texto_docx(z)
            if ext in (".pptx", ".pptm"):
                return _texto_pptx(z)
            if ext in (".xlsx", ".xlsm"):
                return _texto_xlsx(z)
            return _texto_odf(z)
    except (zipfile.BadZipFile, OSError, ET.ParseError, KeyError, ValueError):
        # KeyError: zip sin la entrada esperada; ValueError: bytes no UTF-8 del XML.
        return None


def _texto_pdf(ruta: str):
    """Texto de las primeras MAX_PAGINAS_PDF páginas, unido por renglón.

    Import de pypdf perezoso: mientras no haga falta, no se desempaca nada
    (y si faltara la librería, el PDF queda con búsqueda solo por nombre).
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    import logging
    # Los avisos de pypdf (EOF marker not found, etc.) van al stderr de la
    # consola y solo ensucian; de los errores reales nos ocupamos con None.
    logging.getLogger("pypdf").setLevel(logging.CRITICAL)
    from pypdf.errors import PdfReadError
    try:
        lector = PdfReader(ruta)
        paginas = lector.pages[:MAX_PAGINAS_PDF]
        return "\n".join(pagina.extract_text() or "" for pagina in paginas).strip()
    except (PdfReadError, OSError, ValueError):
        return None


def _texto_docx(z):
    """Párrafos de Word: cada `w:p` una línea, cada `w:t` su texto."""
    raiz = ET.fromstring(z.read("word/document.xml"))
    trozos = []
    for e in raiz.iter():
        if e.tag.endswith("}p"):
            trozos.append("\n")
        elif e.tag.endswith("}t") and e.text:
            trozos.append(e.text)
    return "".join(trozos).strip()


def _texto_pptx(z):
    """Diapositivas de PowerPoint en orden numérico, unidas por espacio."""
    slides = []
    for nombre in z.namelist():
        m = _SLIDE_AION.match(nombre)
        if m:
            slides.append((int(m.group(1)), nombre))
    slides.sort()
    trozos = []
    for _, nombre in slides:
        raiz = ET.fromstring(z.read(nombre))
        trozos.extend(e.text or "" for e in raiz.iter() if e.tag.endswith("}t"))
    return " ".join(trozos).strip()


def _texto_xlsx(z):
    """Celdas de Excel: cadenas compartidas + literales inline, una por línea."""
    trozos = []
    if "xl/sharedStrings.xml" in z.namelist():
        raiz = ET.fromstring(z.read("xl/sharedStrings.xml"))
        trozos.extend(e.text or "" for e in raiz.iter() if e.tag.endswith("}t"))
    for nombre in z.namelist():
        if _HOJA_AION.match(nombre):
            raiz = ET.fromstring(z.read(nombre))
            for e in raiz.iter():
                if e.tag.endswith("}is"):
                    trozos.extend(t.text or "" for t in e.iter() if t.tag.endswith("}t"))
    return "\n".join(trozos).strip()


def _texto_odf(z):
    """Texto plano de ODF (.odt/.ods/.odp): todo el contenido de content.xml."""
    raiz = ET.fromstring(z.read("content.xml"))
    return "".join(raiz.itertext()).strip()
