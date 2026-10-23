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


test_capa()
print("OK indice: capa sqlite")


# ------------------------------------------------ pasar de índice (tarea 5)

import datetime as dt
import os
import queue
import threading

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_texto import fabrica_docx  # noqa: E402

from buscador.escaner import Registro  # noqa: E402


def _registro_de(p):
    st = p.stat()
    return Registro(
        ruta=str(p),
        nombre=p.name,
        tipo="Word",
        tamano=st.st_size,
        creado=dt.datetime.fromtimestamp(st.st_ctime),
        modificado=dt.datetime.fromtimestamp(st.st_mtime),
        nombre_min=p.name.casefold(),
    )


def _progreso(cola):
    """Drena la cola y separa el último progreso del fin."""
    mensajes = []
    while not cola.empty():
        mensajes.append(cola.get())
    fin = mensajes[-1]
    progresos = [m for m in mensajes if m[0] == "indice"]
    return fin, (progresos[-1] if progresos else None), mensajes


def test_pasada():
    import buscador.texto as texto
    from buscador.indice import pasada_indice

    tmp = Path(tempfile.mkdtemp(prefix="buscador_pasada_"))
    raices = ("raiz/de/prueba",)
    try:
        docs = []
        for i, texto_doc in enumerate(["prueba uno", "prueba dos", "otra cosa"], 1):
            p = tmp / f"doc{i}.docx"
            fabrica_docx(texto_doc, p)
            docs.append(p)
        registros = [_registro_de(p) for p in docs]

        cola = queue.Queue()
        pasada_indice(raices, registros, cola, 7, threading.Event())

        fin, prog, _ = _progreso(cola)
        assert fin == ("indice_fin", 7, raices), fin
        assert prog is not None, "falta progreso al final de la pasada"
        assert prog[1] == 7 and prog[2] == raices, prog
        assert prog[3] == 3 and prog[4] == 3 and prog[5] == 0, prog  # hechos/total/sin_texto

        bd = indice.abrir_bd(indice.ruta_indice(raices))
        halladas = indice.buscar_ph(bd, "prueba")
        assert sorted(halladas) == sorted(str(p) for p in docs[:2]), halladas
        bd.close()

        # segunda pasada con lo mismo: nada que hacer (incremental)
        cola = queue.Queue()
        pasada_indice(raices, registros, cola, 8, threading.Event())
        fin, prog, _ = _progreso(cola)
        assert fin == ("indice_fin", 8, raices), fin
        assert prog[3] == 0, prog
        bd = indice.abrir_bd(indice.ruta_indice(raices))
        assert len(indice.buscar_ph(bd, "prueba")) == 2, bd.close()

        # reescribir uno: solo ese se re-lee
        fabrica_docx("kilo sobre mesa", docs[0])
        registros = [_registro_de(p) for p in docs]
        cola = queue.Queue()
        pasada_indice(raices, registros, cola, 9, threading.Event())
        _, prog, _ = _progreso(cola)
        assert prog[3] == 1, prog
        bd = indice.abrir_bd(indice.ruta_indice(raices))
        assert indice.buscar_ph(bd, "kilo") == [str(docs[0])]
        assert indice.buscar_ph(bd, "prueba uno") == []

        # borrar del disco y saneo con la lista sin él
        os.unlink(docs[2])
        registros = [_registro_de(p) for p in docs[:2]]
        cola = queue.Queue()
        pasada_indice(raices, registros, cola, 10, threading.Event())
        _, prog, _ = _progreso(cola)
        assert prog[3] == 0, prog
        assert indice.buscar_ph(bd, "otra cosa") == []
        # doc0 ahora es "kilo sobre mesa" y doc2 se fue: queda solo doc1
        assert indice.buscar_ph(bd, "prueba") == [str(docs[1])], indice.buscar_ph(bd, "prueba")
        bd.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pasada_grande_omitida():
    import buscador.texto as texto
    from buscador.indice import pasada_indice

    tmp = Path(tempfile.mkdtemp(prefix="buscador_grande_"))
    raices = ("otra/raiz",)
    try:
        p = tmp / "grande.docx"
        fabrica_docx("enorme", p)
        registros = [_registro_de(p)]
        original = texto.MAX_TAMANO_ARCHIVO
        texto.MAX_TAMANO_ARCHIVO = 100
        try:
            cola = queue.Queue()
            pasada_indice(raices, registros, cola, 3, threading.Event())
            fin, prog, _ = _progreso(cola)
            assert fin == ("indice_fin", 3, raices), fin
            assert prog[3] == 0 and prog[4] == 0, prog  # nada candidato
        finally:
            texto.MAX_TAMANO_ARCHIVO = original
        bd = indice.abrir_bd(indice.ruta_indice(raices))
        try:
            assert indice.buscar_ph(bd, "enorme") == []
        finally:
            bd.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_pasada_cancelada():
    from buscador.indice import pasada_indice

    tmp = Path(tempfile.mkdtemp(prefix="buscador_cancel_"))
    raices = ("raiz/corta",)
    try:
        p = tmp / "nuevo.docx"
        fabrica_docx("palabra flamante", p)
        registros = [_registro_de(p)]

        colas = queue.Queue()
        cancelar = threading.Event()
        cancelar.set()
        pasada_indice(raices, registros, colas, 5, cancelar)

        fin, prog, mensajes = _progreso(colas)
        assert fin == ("indice_fin", 5, raices), fin
        assert prog is None, mensajes  # sin progreso al cancelar
        bd = indice.abrir_bd(indice.ruta_indice(raices))
        try:
            assert indice.buscar_ph(bd, "palabra") == []
        finally:
            bd.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


test_pasada()
test_pasada_grande_omitida()
test_pasada_cancelada()
print("OK indice: pasada con pool")

shutil.rmtree(TMP, ignore_errors=True)
