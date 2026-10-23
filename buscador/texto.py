"""Texto: normalización (buscar sin tildes, 1:1) y extracción de contenido.

`normalizar` es la base del filtrado por nombre y del índice de contenido:
ambas búsquedas deben responder igual escriba el usuario con o sin acentos.
Garantía clave: la salida SIEMPRE mide lo mismo que la entrada (por eso no
se usa ni str.casefold() — 'ß'.casefold() == 'ss' — ni una descomposición
NFD recortada, que cambia larguras).
"""

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
