# indice: capa sqlite — roundtrip, escapes SQL del plan y saneo de rutas.
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buscador.indice as indice

TMP = Path(tempfile.mkdtemp(prefix="buscador_idx_"))
# La carpeta de caché se redirige ANTES de abrir la bd (quirk de pruebas).
indice._carpeta_cache = lambda: TMP


def test_capa():
    raices = ("unidad:/prueba",)
    clave = hashlib.sha1(repr(raices).encode("utf-8")).hexdigest()[:8]

    ruta_bd = indice.ruta_indice(raices)
    assert ruta_bd.parent == TMP, ruta_bd
    assert ruta_bd.name == f"indice_{clave}.db", ruta_bd

    bd = indice.abrir_bd(ruta_bd)
    indice.guardar_doc(bd, "a.docx", 5.0, 100, "Hola Información")
    indice.guardar_doc(bd, "a.pdf", 1.0, 10, "precio 50% variado stocks 2026")
    bd.commit()

    version = bd.execute("SELECT valor FROM meta WHERE clave='version'").fetchone()
    assert version and version[0] == "1", version

    # ¿está y está al día?
    assert indice.existe_actualizada(bd, "a.docx", 5.0, 100) is True
    assert indice.existe_actualizada(bd, "a.docx", 6.0, 100) is False
    assert indice.existe_actualizada(bd, "a.docx", 5.0, 101) is False
    assert indice.existe_actualizada(bd, "noexiste.docx", 5.0, 100) is False

    # roundtrip: el texto original (con tildes) sale tal cual
    assert indice.texto_de(bd, "a.docx") == "Hola Información"
    assert indice.texto_de(bd, "noexiste.docx") == ""

    # sin tildes consulta y contenido se igualan
    assert indice.buscar_ph(bd, "informacion") == ["a.docx"]

    # escapes fijados por el plan: % y _ literales de la consulta NO son comodines;
    # ? y * del usuario sí
    assert indice.buscar_ph(bd, "50%") == ["a.pdf"]
    assert indice.buscar_ph(bd, "stocks_2026") == []
    assert indice.buscar_ph(bd, "stocks?2026") == ["a.pdf"]
    assert indice.buscar_ph(bd, "precio*") == ["a.pdf"]

    # el patrón escapa literales ANTES de traducir comodines
    assert indice.patron_sql("a?b*c\\d") == "a_b%c\\\\d"

    # saneo: filas de rutas muertas
    indice.guardar_doc(bd, "borrame.pdf", 1.0, 5, "desaparecido")
    bd.commit()
    n = indice.limpiar_bd(bd, {"a.docx", "a.pdf"})
    assert n == 1, n
    assert indice.buscar_ph(bd, "desaparecido") == []
    assert indice.buscar_ph(bd, "informacion") == ["a.docx"]

    bd.close()
    shutil.rmtree(TMP, ignore_errors=True)


test_capa()
print("OK indice: capa sqlite")
