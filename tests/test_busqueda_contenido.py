# Búsqueda por contenido: pasada automática al abrir una caché y estado
# en la barra ("índice: listo"); mensajes de generaciones viejas ignorados.
import asyncio
import datetime as dt
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import buscador.escaner as esc
import buscador.indice as indice
from buscador import app as app_mod
from buscador.app import BuscadorApp
from buscador.escaner import Registro
from test_texto import fabrica_docx  # escribe docx reales (zip+xml)

TMP = Path(tempfile.mkdtemp(prefix="buscador_contenido_"))
app_mod._ruta_preferencias = lambda: TMP / "preferencias.json"
esc._carpeta_cache = lambda: TMP
indice._carpeta_cache = lambda: TMP

DOC = TMP / "Informe ÍNTIMO.docx"
fabrica_docx("kilo pan sobre mesa", DOC)
st = DOC.stat()
RAICES = (str(TMP),)

REG = Registro(
    ruta=str(DOC),
    nombre=DOC.name,
    tipo="Word",
    tamano=st.st_size,
    creado=dt.datetime.fromtimestamp(st.st_ctime),
    modificado=dt.datetime.fromtimestamp(st.st_mtime),
    nombre_min="informe intimo.docx",
)
esc.guardar_cache(RAICES, [REG])


async def main():
    try:
        # --- la caché dispara la pasada de índice al arrancar ---
        app = BuscadorApp(raices=RAICES)
        app._comenzar_escaneo = lambda: None  # ANTES de run_text (quirk AGENTS)
        async with app.run_test(size=(120, 25)) as pilot:
            listo = False
            for _ in range(100):  # ≤ 10 s de espera de la pasada
                await asyncio.sleep(0.1)
                if app._estado_indice and app._estado_indice[0] == "listo":
                    listo = True
                    break
            assert listo, app._estado_indice
            estado = str(app.query_one("#estado").render())
            assert "índice: listo" in estado, estado

            # --- mensajes de una generación vieja: ignorados ---
            anterior = app._estado_indice
            app.cola.put(("indice", 999, ("xa:",), 1, 1, 0))
            app.cola.put(("indice_fin", 999, ("xa:",)))
            for _ in range(10):
                await asyncio.sleep(0.1)
            assert app._estado_indice == anterior, app._estado_indice
        print("OK contenido: pasada automatica al abrir cache + estado 'listo'")

        # --- el documento quedó SANEADO en el índice del ámbito ---
        bd = indice.abrir_bd(indice.ruta_indice(RAICES))
        assert indice.buscar_ph(bd, "kilo") == [str(DOC)], indice.buscar_ph(bd, "kilo")
        bd.close()
        print("OK contenido: el docx de la caché quedó indexado")
    finally:
        shutil.rmtree(TMP, ignore_errors=True)


asyncio.run(main())
print("OK contenido: pasada automatica + estado listo + indexado")


# --------------------------------------------------------------- union (tarea 8)

import buscador.indice as indice2  # noqa: E402  (mismo módulo, otra carpeta TMP)

TMP2 = Path(tempfile.mkdtemp(prefix="buscador_union_"))
esc._carpeta_cache = lambda: TMP2
indice._carpeta_cache = lambda: TMP2
from buscador.indice import abrir_bd, guardar_doc, ruta_indice  # noqa: E402

FONDO = TMP2 / "informe anual.docx"  # el nombre NO menciona "presupuesto"
fabrica_docx("presupuesto especial revisado", FONDO)
st2 = FONDO.stat()
RAICES2 = (str(TMP2),)
REG2 = Register = Registro(
    ruta=str(FONDO),
    nombre=FONDO.name,
    tipo="Word",
    tamano=st2.st_size,
    creado=dt.datetime.fromtimestamp(st2.st_ctime),
    modificado=dt.datetime.fromtimestamp(st2.st_mtime),
    nombre_min="informe anual.docx",
)
esc.guardar_cache(RAICES2, [REG2])
# DB sembrada a mano con el texto (la pasada de la app lo dejará igual: incremental)
bd = abrir_bd(ruta_indice(RAICES2))
guardar_doc(bd, str(FONDO), st2.st_mtime, st2.st_size, "presupuesto especial revisado")
bd.commit()
bd.close()


async def main_union():
    try:
        app = BuscadorApp(raices=RAICES2)
        app._comenzar_escaneo = lambda: None
        async with app.run_test(size=(120, 25)) as pilot:
            await pilot.pause()
            entrada = app.query_one("#entrada")

            # entra por contenido aunque su nombre no lo diga
            entrada.value = "presupuesto"
            await pilot.pause()
            assert [r.ruta for r in app._encontradas()] == [str(FONDO)], app._encontradas()
            assert app._coincidencias == {str(FONDO)}, app._coincidencias

            # sin texto: nadie entra por contenido
            entrada.value = ""
            await pilot.pause()
            assert app._coincidencias is None, app._coincidencias

            # filtro de solo PDF: el docx (Word) desaparece
            entrada.value = "presupuesto"
            await pilot.pause()
            app.action_filtro_pdf()
            await pilot.pause()
            assert app._encontradas() == [], app._encontradas()
            app.action_filtro_pdf()  # apaga el filtro
            await pilot.pause()

            # comodín: 'presu*' también lo encuentra (por contenido)
            entrada.value = "presu*"
            await pilot.pause()
            assert [r.ruta for r in app._encontradas()] == [str(FONDO)], app._encontradas()
        print("OK union: nombre + contenido filtran juntos (texto, vacio, F6, comodin)")
    finally:
        shutil.rmtree(TMP2, ignore_errors=True)


asyncio.run(main_union())
print("TODO OK")
