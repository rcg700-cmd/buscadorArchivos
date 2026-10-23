# normalizar(): minúsculas sin tildes, 1:1, longitud preservada.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_normalizar():
    from buscador.texto import normalizar

    assert normalizar("INFORMACIÓN") == "informacion"
    assert normalizar("Informe Íntimo") == "informe intimo"
    s = "áéíóúüñÁÉÍÓÚÜÑçÇgG"
    assert len(normalizar(s)) == len(s)
    assert normalizar("aäå") == "aaa"


test_normalizar()
print("OK normalizar")


# ---------------------------------------------------------------- extraer_texto

import shutil
import tempfile
import zipfile

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
X_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
O_NS = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
T_NS = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"


def _zip_a(ruta, entradas):
    """Escribe un zip real con las `(nombre, contenido)` dadas."""
    with zipfile.ZipFile(ruta, "w") as z:
        for nombre, contenido in entradas:
            z.writestr(nombre, contenido)


def fabrica_docx(texto, ruta):
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        f"<w:p><w:r><w:t>{texto}</w:t></w:r></w:p>"
        "</w:body></w:document>"
    )
    _zip_a(ruta, [("word/document.xml", doc)])


def fabrica_pptx(ruta, textos):
    entradas = []
    for i, texto in enumerate(textos, 1):
        slide = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:a="{P_NS}">'
            f"<p:cSld><p:txBody><a:p><a:r><a:t>{texto}</a:t></a:r></a:p></p:txBody></p:cSld></p:sld>"
        )
        entradas.append((f"ppt/slides/slide{i}.xml", slide))
    _zip_a(ruta, entradas)


def fabrica_xlsx(ruta, textos, inline=None):
    si = "".join(f"<si><t>{t}</t></si>" for t in textos)
    compartidas = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="{X_NS}">{si}</sst>'
    )
    hoja = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{X_NS}"><sheetData>'
        + (
            f'<row r="2"><c r="A2" t="inlineStr"><is><t>{inline}</t></is></c></row></sheetData>'
            if inline
            else "</sheetData>"
        )
        + "</worksheet>"
    )
    _zip_a(ruta, [("xl/sharedStrings.xml", compartidas), ("xl/worksheets/sheet1.xml", hoja)])


def fabrica_odt(texto, ruta):
    contenido = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<office:document-content xmlns:office="{O_NS}" xmlns:text="{T_NS}">'
        f"<office:body><office:text><text:p>{texto}</text:p></office:text></office:body>"
        "</office:document-content>"
    )
    _zip_a(ruta, [("content.xml", contenido)])


def test_extraccion_office():
    from buscador.texto import extraer_texto

    tmp = Path(tempfile.mkdtemp(prefix="buscador_extrae_"))
    try:
        docx = tmp / "hola.docx"
        fabrica_docx("Hola mundo docx", docx)
        assert extraer_texto(str(docx)) == "Hola mundo docx", extraer_texto(str(docx))

        odt = tmp / "hola.odt"
        fabrica_odt("Hola mundo odt", odt)
        assert extraer_texto(str(odt)) == "Hola mundo odt", extraer_texto(str(odt))

        pptx = tmp / "mazo.pptx"
        fabrica_pptx(pptx, ["slide uno", "slide dos"])
        p = extraer_texto(str(pptx))
        assert "slide uno" in p and "slide dos" in p, p

        xlsx = tmp / "hoja.xlsx"
        fabrica_xlsx(xlsx, ["celda uno", "otra"], inline="inline texto")
        x = extraer_texto(str(xlsx))
        assert "celda uno" in x and "otra" in x and "inline texto" in x, x

        # formato viejo: solo por nombre, sin contenido
        doc = tmp / "viejo.doc"
        _zip_a(doc, [("nada", "nada")])
        assert extraer_texto(str(doc)) is None

        # zip corrupto (bytes a la mitad): None sin excepción
        roto = tmp / "roto.docx"
        fabrica_docx("algo", roto)
        data = roto.read_bytes()
        roto.write_bytes(data[: len(data) // 2])
        assert extraer_texto(str(roto)) is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


test_extraccion_office()
print("OK extraer_texto office")
