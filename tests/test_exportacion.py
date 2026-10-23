# Ctrl+E: exporta los resultados filtrados actuales a un CSV.
import asyncio
import csv as csv_mod
import datetime as dt
import os
import pathlib
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buscador import app as app_mod
from buscador.app import BuscadorApp, exportar_csv
from buscador.escaner import Registro

tmp = pathlib.Path(tempfile.mkdtemp(prefix="buscador_csv_"))
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


datos = [
    registro("informe.docx", r"C:\Docs"),
    registro("informe.docx", r"C:\Copia"),
    registro("plan 2026.xlsx", r"C:\Docs", tipo="Excel"),
    registro("unico.pdf", r"C:\Otros", tipo="PDF"),
    registro("punto y coma ;.docx", r"C:\Docs"),  # fuerza el escapado del CSV
]

app = BuscadorApp(raices=(r"C:\\",))
app._comenzar_escaneo = lambda: None


async def main():
    try:
        # --- exportar_csv escribe encabezados + filas con ';' y BOM UTF-8
        destino = tmp / "salida.csv"
        exportar_csv(datos, destino)
        crudo = destino.read_bytes()
        assert crudo.startswith(b"\xef\xbb\xbf"), "el CSV debe traer BOM UTF-8"
        filas = list(csv_mod.reader(crudo.decode("utf-8-sig").splitlines(), delimiter=";"))
        assert filas[0] == ["Nombre", "Tipo", "Creado", "Modificado", "Peso (bytes)", "Carpeta", "Ruta completa"], filas[0]
        assert filas[5] == [
            "punto y coma ;.docx", "Word", "01/10/2026 00:00", "01/10/2026 00:00",
            "1000", r"C:\Docs", os.path.join(r"C:\Docs", "punto y coma ;.docx"),
        ], filas[5]
        assert len(filas) == len(datos) + 1, filas
        print("OK exportar_csv: BOM, ';' y escape de comillas correctos")

        # --- las celdas que empiezan por =,+,-,@ se citan con apóstrofe
        # (inyección de fórmulas al abrir el CSV en Excel)
        peligro = tmp / "peligro.csv"
        exportar_csv(
            [
                registro("=ejecuta().docx", r"C:\Descargas"),
                registro("+suma.docx", r"C:\Descargas"),
                registro("inocente.docx", r"@carpeta"),
            ],
            peligro,
        )
        p = list(csv_mod.reader(peligro.read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
        assert p[1][0] == "'=ejecuta().docx", p[1]
        assert p[2][0] == "'+suma.docx", p[2]
        assert p[3][6].startswith("'@"), p[3]  # la ruta completa con carpeta peligrosa
        assert p[3][0] == "inocente.docx", p[3]  # lo normal no se toca
        print("OK exportar_csv: apóstrofe contra fórmulas de Excel")

        async with app.run_test(size=(120, 30)) as pilot:
            app.registros = list(datos)
            app.rutas_conocidas = {r.ruta for r in datos}
            app.de_cache = True
            app._firma = None
            app._refrescar()
            await pilot.pause()

            # --- Ctrl+E respeta el filtro de texto y el orden actual
            app.texto = "informe"
            app.orden = ("nombre", False)
            app._firma = None
            app._refrescar()
            await pilot.pause()
            assert len(app.mostradas) == 2, app.mostradas

            # redirigimos la carpeta destino al temporal para no ensuciar el Escritorio
            app_mod.carpeta_exportacion = lambda: tmp
            await pilot.press("ctrl+e")
            await pilot.pause()
            avisos = [n for n in app._notifications if "Exportados 2" in str(n.message)]
            assert avisos, str([str(n.message) for n in app._notifications])
            csvs = list(tmp.glob("buscador_resultados_*.csv"))
            assert len(csvs) == 1, csvs
            filas = list(csv_mod.reader(csvs[0].read_text(encoding="utf-8-sig").splitlines(), delimiter=";"))
            assert len(filas) == 3, filas  # encabezado + los 2 "informe"
            assert all(x[0] == "informe.docx" for x in filas[1:]), filas
            print("OK Ctrl+E: exporta solo lo filtrado (2 de 5) al CSV con aviso")

            # --- sin resultados avisa y no escribe nada
            app.texto = "nada-de-nada"
            app._firma = None
            app._refrescar()
            await pilot.pause()
            await pilot.press("ctrl+e")
            await pilot.pause()
            assert len(list(tmp.glob("buscador_resultados_*.csv"))) == 1, "no debe crear más CSV"
            warn = [n for n in app._notifications if n.severity == "warning" and "exportar" in str(n.message).casefold()]
            assert warn, str([str(n.message) for n in app._notifications])
            print("OK Ctrl+E: sin resultados avisa y no crea archivos")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("TODO OK")


asyncio.run(main())
