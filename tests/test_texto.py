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


# ---------------------------------------------------------------- extraer_texto PDF

PDF_CAB = b"%PDF-1.4\n"


def fabrica_pdf(textos, ruta):
    """PDF válido sin compresión: un stream `(texto) Tj` por página, xref a mano."""
    n = len(textos)
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + 2 * i + 1} 0 R" for i in range(n))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("latin-1"))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, texto in enumerate(textos):
        stream = f"BT /F1 12 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
        objs.append(
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)
        )
        objs.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {4 + 2 * i} 0 R >>".encode(
                "latin-1"
            )
        )
    out = bytearray(PDF_CAB)
    offsets = []
    for idx, cuerpo in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode("latin-1") + cuerpo + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode("latin-1")
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    Path(ruta).write_bytes(bytes(out))


def test_extraccion_pdf():
    import buscador.texto as texto_mod
    from buscador.texto import extraer_texto

    tmp = Path(tempfile.mkdtemp(prefix="buscador_pdf_"))
    try:
        # las 3 páginas están
        pdf = tmp / "tres.pdf"
        fabrica_pdf(["pagina uno", "pagina dos", "pagina tres"], pdf)
        t = extraer_texto(str(pdf))
        assert "pagina uno" in t and "pagina dos" in t and "pagina tres" in t, t

        # tope de páginas: la 3 queda fuera
        original_paginas = texto_mod.MAX_PAGINAS_PDF
        texto_mod.MAX_PAGINAS_PDF = 2
        try:
            t2 = extraer_texto(str(pdf))
            assert "pagina uno" in t2 and "pagina dos" in t2, t2
            assert "pagina tres" not in t2, t2
        finally:
            texto_mod.MAX_PAGINAS_PDF = original_paginas

        # tope de tamaño: con el límite en 10 bytes, un PDF real no entra
        original_tamano = texto_mod.MAX_TAMANO_ARCHIVO
        texto_mod.MAX_TAMANO_ARCHIVO = 10
        try:
            assert extraer_texto(str(pdf)) is None
        finally:
            texto_mod.MAX_TAMANO_ARCHIVO = original_tamano

        # PDF truncado: None sin excepción
        roto = tmp / "roto.pdf"
        fabrica_pdf(["algo"], roto)
        data = roto.read_bytes()
        roto.write_bytes(data[: len(data) // 2])
        assert extraer_texto(str(roto)) is None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


test_extraccion_pdf()
print("OK extraer_texto pdf")
