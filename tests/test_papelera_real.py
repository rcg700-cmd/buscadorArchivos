# Flujo REAL Ctrl+Supr: archivo real en disco, diálogo con clic en "Sí".
import asyncio
import datetime as dt
import os
import pathlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from textual.widgets import Button

import buscador.app as app_mod
from buscador.app import BuscadorApp, ConfirmarScreen
from buscador.escaner import Registro

base = pathlib.Path(tempfile.gettempdir()) / "buscador_tests"
base.mkdir(parents=True, exist_ok=True)
app_mod._ruta_preferencias = lambda: base / "preferencias.json"

f = base / "papelera_flujo_real.txt"
f.write_text("contenido de prueba")
st = f.stat()


async def main():
    app = BuscadorApp(raices=(str(base),))
    app._comenzar_escaneo = lambda: None
    reg = Registro(
        ruta=str(f), nombre=f.name, tipo="Word", tamano=st.st_size,
        creado=dt.datetime.fromtimestamp(st.st_ctime),
        modificado=dt.datetime.fromtimestamp(st.st_mtime), nombre_min=f.name.casefold(),
    )
    async with app.run_test(size=(120, 30)) as pilot:
        app.registros = [reg]
        app.rutas_conocidas = {str(f)}
        app.de_cache = True
        app._firma = None
        app._refrescar()
        await pilot.pause()
        assert len(app.mostradas) == 1

        await pilot.press("ctrl+delete")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmarScreen)
        await pilot.click("#si")  # clic REAL en el botón "Sí, enviar"
        for _ in range(40):
            await pilot.pause(0.05)
            if not os.path.exists(str(f)):
                break
        assert not os.path.exists(str(f)), "el archivo sigue en disco"
        assert len(app.registros) == 0, app.registros
        assert len(app.mostradas) == 0
        estado = str(app.query_one("#estado").render())
        assert "Encontrados" in estado
        print("OK flujo real: clic en Si borra el archivo y la fila de la lista")

    # --- fallo del backend de papelera: (False, False), nunca excepción
    original = app_mod._borrar_papelera_windows
    if os.name == "nt":
        for error in (ValueError("nul"), OSError("winerror")):
            def romper(_ruta, _error=error):
                raise _error
            app_mod._borrar_papelera_windows = romper
            ok, en_papelera = app_mod._enviar_papelera(r"C:\no\importa")
            assert not ok and not en_papelera, (ok, en_papelera)
        del romper
    app_mod._borrar_papelera_windows = original
    print("OK _enviar_papelera: fallo del backend se traduce en (False, False)")

    shutil.rmtree(base, ignore_errors=True)
    print("TODO OK")

    shutil.rmtree(base, ignore_errors=True)
    print("TODO OK")


asyncio.run(main())
