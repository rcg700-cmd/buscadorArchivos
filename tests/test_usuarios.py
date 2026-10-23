# Selector de usuario (ctrl+u): elegir usuario / todos los usuarios / todo el disco.
import asyncio
import json
import pathlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from textual.widgets import ListView

import buscador.app as app_mod
from buscador.app import BuscadorApp, UsuarioScreen

tmp = pathlib.Path(tempfile.mkdtemp(prefix="buscador_usu_"))
app_mod._ruta_preferencias = lambda: tmp / "preferencias.json"

# Dos "usuarios" de prueba, cada uno con un archivo Office
base_users = tmp / "MisUsuarios"
usuarios = []
for nombre in ("ana", "pedro"):
    d = base_users / nombre
    (d / "docs").mkdir(parents=True)
    f = d / "docs" / f"informe_{nombre}.docx"
    f.write_text("x")
    usuarios.append(d)


app_mod._usuarios_del_sistema = lambda: (base_users, usuarios)

app = BuscadorApp()
app._comenzar_escaneo = lambda: None


async def main():
    async with app.run_test(size=(130, 36)) as pilot:
        await pilot.pause()
        assert app.raices == tuple(app_mod.raices_por_defecto()), "arranque limpio (sin prefs) = todo el disco"

        # --- ctrl+u abre el panel con las opciones esperadas
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert isinstance(app.screen, UsuarioScreen), type(app.screen)
        datos = [it.data for it in app.screen.query_one("#lista", ListView).children]
        assert datos[0] is None, "primera opción = todo el disco"
        assert datos[1] == base_users, "segunda = todos los usuarios"
        assert set(datos[2:]) == set(usuarios), "después, cada usuario"
        print("OK ctrl+u abre selector con 'todo el disco', 'todos' y usuarios")

        # --- elegir "todos los usuarios": desde index None, 2 downs marcan el 1
        lista = app.screen.query_one("#lista", ListView)
        lista.focus()
        await pilot.press("down", "down", "enter")
        await pilot.pause()
        assert app.raices == (str(base_users),), app.raices
        await pilot.pause(0.3)

        # --- ctrl+u de nuevo y elegir el usuario 'pedro': 4 downs → índice 3
        await pilot.press("ctrl+u")
        await pilot.pause()
        assert isinstance(app.screen, UsuarioScreen)
        lista = app.screen.query_one("#lista", ListView)
        lista.focus()
        await pilot.press("down", "down", "down", "down", "enter")
        await pilot.pause()
        assert app.raices == (str(usuarios[1]),), app.raices
        print("OK ctrl+u: 'todos los usuarios' y usuario concreto cambian el ámbito")

        # --- la preferencia quedó guardada (raices)
        prefs = json.loads((tmp / "preferencias.json").read_text(encoding="utf-8"))
        assert prefs.get("raices") == [str(usuarios[1])], prefs
        print("OK ctrl+u: el ámbito elegido se recuerda en preferencias.json")

    # --- nueva sesión: arranca con el último ámbito guardado
    prefs = {"raices": [str(usuarios[0])], "tema": "textual-dark"}
    (tmp / "preferencias.json").write_text(json.dumps(prefs), encoding="utf-8")
    app2 = BuscadorApp()
    app2._comenzar_escaneo = lambda: None
    async with app2.run_test(size=(130, 30)) as pilot:
        await pilot.pause()
        assert app2.raices == (str(usuarios[0]),), f"no recuperó el ámbito: {app2.raices}"
        print("OK arranque recupera el último ámbito (usuario 'ana')")

    shutil.rmtree(tmp, ignore_errors=True)
    print("TODO OK")


asyncio.run(main())
