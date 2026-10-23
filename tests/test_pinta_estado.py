# La barra de estado debe consultar las raíces por defecto UNA vez por
# sesión (hoy las consulta en cada repintado: 26 llamadas a os.path.exists
# por letra de unidad en Windows, varias veces por segundo durante un escaneo).
import asyncio
import pathlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buscador import app as app_mod
from buscador.app import BuscadorApp

tmp = pathlib.Path(tempfile.mkdtemp(prefix="buscador_estado_"))
app_mod._ruta_preferencias = lambda: tmp / "preferencias.json"

llamadas = {"n": 0}


def contada():
    llamadas["n"] += 1
    return ("D:\\",)


async def main():
    try:
        original = app_mod.raices_por_defecto
        app_mod.raices_por_defecto = contada
        app = BuscadorApp(raices=("E:\\Docs",))
        app._comenzar_escaneo = lambda: None
        async with app.run_test(size=(120, 25)) as pilot:
            await pilot.pause()
            # Tres repintados del estado (los repintados reales llegan así:
            # _refrescar al filtrar y _recibir con cada latido de progreso)
            app._firma = None
            app._refrescar()
            await pilot.pause()
            app._pinta_estado(0, 0)
            app._pinta_estado(0, 0)
            assert llamadas["n"] == 1, f"raices_por_defecto se llamó {llamadas['n']} veces; debe ser 1 por sesión"
        print("OK _pinta_estado: 1 consulta de raices_por_defecto por sesión")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


asyncio.run(main())
