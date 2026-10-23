# Vigilancia: archivos borrados FUERA del programa desaparecen de la lista solos.
import asyncio
import datetime as dt
import pathlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buscador.app as app_mod
from buscador.app import BuscadorApp
from buscador.escaner import Registro

base = pathlib.Path(tempfile.gettempdir()) / "buscador_tests" / "vigilancia"
base.mkdir(parents=True, exist_ok=True)
app_mod._ruta_preferencias = lambda: base.parent / "preferencias.json"


def ficha(nombre):
    f = base / nombre
    f.write_text("prueba vigilancia")
    st = f.stat()
    return f, Registro(
        ruta=str(f), nombre=f.name, tipo="Word", tamano=st.st_size,
        creado=dt.datetime.fromtimestamp(st.st_ctime),
        modificado=dt.datetime.fromtimestamp(st.st_mtime),
        nombre_min=f.name.casefold(),
    )


f1, r1 = ficha("queda.txt")
f2, r2 = ficha("desaparece.txt")

app = BuscadorApp(raices=(str(base),))
app._comenzar_escaneo = lambda: None


async def main():
    async with app.run_test(size=(120, 30)) as pilot:
        app.registros = [r1, r2]
        app.rutas_conocidas = {r1.ruta, r2.ruta}
        app.de_cache = False
        app._firma = None
        app._refrescar()
        await pilot.pause()
        assert len(app.mostradas) == 2

        # Chequeo con los dos presentes: no debe quitar nada
        app._vigilar()
        for _ in range(40):
            await pilot.pause(0.05)
            if not app._vigilando and len(app.registros) == 2:
                break
        assert len(app.registros) == 2 and len(app.mostradas) == 2
        print("OK vigilancia: nada desaparece si los archivos existen")

        # El usuario borra "desaparece.txt" desde el Explorador (simulado)
        f2.unlink()
        app._vigilar()
        for _ in range(60):
            await pilot.pause(0.05)
            if len(app.registros) == 1:
                break
        assert len(app.registros) == 1, f"quedan {len(app.registros)}"
        assert r2.ruta in app._rutas_borradas
        assert r1.ruta in {r.ruta for r in app.registros}
        print("OK vigilancia: el borrado externo saca la fila de la lista solita")

        # Un resultado de validación antiguo no resucita al borrado externo
        app.cola.put(("validadas", app._generacion, app.raices, [r1, r2], 1))
        app._recibir()
        await pilot.pause()
        assert r2.ruta not in {r.ruta for r in app.registros}
        assert len(app.registros) == 1
        print("OK vigilancia: anti-fantasma con resultados de caché en vuelo")

    shutil.rmtree(base, ignore_errors=True)  # limpieza aparte de la vigilancia
    print("TODO OK")


asyncio.run(main())
