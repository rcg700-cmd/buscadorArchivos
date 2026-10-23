# F10 (solo duplicados) + Ctrl+Supr (papelera con confirmación) — headless.
import asyncio
import datetime as dt
import os
import pathlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buscador.app as app_mod
from buscador.app import BuscadorApp
from buscador.escaner import Registro

tmp = pathlib.Path(tempfile.mkdtemp(prefix="buscador_dup_"))
app_mod._ruta_preferencias = lambda: tmp / "preferencias.json"


def registro(nombre, carpeta, tipo="Word"):
    base = dt.datetime(2026, 10, 1)
    return Registro(
        ruta=os.path.join(carpeta, nombre),
        nombre=nombre,
        tipo=tipo,
        tamano=1000,
        creado=base,
        modificado=base,
        nombre_min=nombre.casefold(),
    )


FOLDERS = [fr"A:\P{1}", fr"A:\P{2}"]
datos = [
    registro("informe.docx", FOLDERS[0]),
    registro("informe.docx", FOLDERS[1]),
    registro("informe.docx", fr"A:\P{3}"),
    registro("unico.pdf", "A:"),
    registro("datos.xlsx", FOLDERS[0]),
    registro("datos.xlsx", FOLDERS[1]),
]
datos.sort(key=lambda r: r.nombre_min)
UNICA = [r for r in datos if r.nombre == "unico.pdf"][0]

app_mod._enviar_papelera = lambda ruta: (True, True)  # simulación (no borra nada real)

app = BuscadorApp(raices=("A:\\",))
app._comenzar_escaneo = lambda: None


async def main():
    async with app.run_test(size=(140, 36)) as pilot:
        await pilot.pause()
        app.registros = list(datos)
        app.rutas_conocidas = {r.ruta for r in datos}
        app.de_cache = True
        app._firma = None
        app._refrescar()
        await pilot.pause()
        assert len(app.mostradas) == 6

        # --- F10 activa duplicados y ordena por nombre
        app.orden = ("tamano", True)
        await pilot.press("f10")
        await pilot.pause()
        assert app.duplicados is True
        assert app.orden == ("nombre", False)

        nombres = [r.nombre for r in app.mostradas]
        assert nombres == ["datos.xlsx", "datos.xlsx", "informe.docx", "informe.docx", "informe.docx"], nombres
        assert "unico.pdf" not in [r.nombre for r in app.mostradas]
        estado = str(app.query_one("#estado").render())
        assert "Duplicados" in estado and "2 grupos" in estado and "5 archivos" in estado
        print("OK F10: solo repetidos (5 archivos de 2 grupos), estado:", estado.encode("ascii", "replace").decode()[:120])

        # --- combinable con texto escrito
        from textual.widgets import Input

        app.query_one("#entrada", Input).focus()
        await pilot.press("i", "n", "f", "o")
        await pilot.pause()
        assert [r.nombre for r in app.mostradas] == ["informe.docx"] * 3, app.mostradas
        app.texto = ""
        app._firma = None
        app._refrescar()
        await pilot.pause()

        # --- F10 desactiva y restaura el orden previo
        await pilot.press("f10")
        await pilot.pause()
        assert app.duplicados is False and app.orden == ("tamano", True), app.orden
        assert len(app.mostradas) == 6
        print("OK F10 off restaura orden previo")

        # --- Ctrl+Supr abre confirmación; Esc = No (no borra)
        await pilot.press("ctrl+delete")
        await pilot.pause()
        from buscador.app import ConfirmarScreen

        assert isinstance(app.screen, ConfirmarScreen), type(app.screen)
        await pilot.press("escape")
        await pilot.pause()
        assert len(app.registros) == 6, "Esc no debe borrar"
        print("OK Ctrl+Supr: Esc cancela sin borrar")

        # --- Confirmación Sí borra: la fila desaparece de la lista sin re-escanear
        app._borrar_resaltado(UNICA)
        await pilot.pause()
        assert UNICA.ruta not in {r.ruta for r in app.registros}, "no se borró"
        assert UNICA.ruta in app._rutas_borradas
        assert len(app.registros) == 5
        # un resultado de validación antiguo no lo resucita
        app.cola.put(("validadas", app._generacion, app.raices, list(datos), 0))
        app._recibir()
        await pilot.pause()
        assert UNICA.ruta not in {r.ruta for r in app.registros}, "un 'validadas' antiguo resucitó el borrado"
        # y la llegada de un escaneo tampoco
        app.cola.put(UNICA)
        app._recibir()
        await pilot.pause()
        assert UNICA.ruta not in {r.ruta for r in app.registros}, "el fantasma volvió por la cola del escaneo"
        print("OK papelera: fila fuera y anti-fantasma (validadas + escaneo)")

    shutil.rmtree(tmp, ignore_errors=True)
    print("TODO OK")

asyncio.run(main())
