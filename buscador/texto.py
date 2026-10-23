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


def normalizar(texto: str) -> str:
    """Minúsculas por carácter + tildes a la base; la longitud no cambia."""
    if not isinstance(texto, str):
        raise TypeError("normalizar espera un str")
    return texto.translate(_TABLA)


# ---------------------------------------------------------------- extracción

# Formatos OOXML/ODF que llevan su contenido en un ZIP de XML internos.
EXTRACCION = {".docx", ".docm", ".pptx", ".pptm", ".xlsx", ".xlsm", ".odt", ".ods", ".odp"}

_SLIDE_AION = re.compile(r"^ppt/slides/slide(\d+)\.xml$")
_HOJA_AION = re.compile(r"^xl/worksheets/sheet\d+\.xml$")


def extraer_texto(ruta: str):
    """Devuelve el texto legible del documento, o None si no se puede extraer.

    Devuelve None para los formatos viejos (.doc/.xls/.ppt: se buscan solo
    por nombre, según el diseño) y para cualquier archivo dañado o ilegible.
    Nunca lanza: los documentos del disco están fuera de nuestro control.
    """
    ext = os.path.splitext(ruta)[1].lower()
    if ext not in EXTRACCION:
        return None
    try:
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
