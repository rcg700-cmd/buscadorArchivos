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
print("TODO OK")
