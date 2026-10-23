# Escaneo real del escáner sobre una carpeta temporal (sin TUI).
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buscador.app  # noqa: F401  (comprobación de import del módulo de la TUI)
from buscador.escaner import iniciar_escaneo


def run():
    base = Path(tempfile.mkdtemp(prefix="buscador_escaner_"))
    (base / "docs").mkdir()
    # un archivo por formato admitido (incluidos los de macro) + uno ajeno
    esperados = {
        "w.doc": "Word", "w.docx": "Word", "w.docm": "Word",
        "e.xls": "Excel", "e.xlsx": "Excel", "e.xlsm": "Excel",
        "p.ppt": "PowerPoint", "p.pptx": "PowerPoint", "p.pptm": "PowerPoint",
        "d.pdf": "PDF",
        "l.odt": "LibreOffice", "l.ods": "LibreOffice", "l.odp": "LibreOffice",
    }
    for nombre in esperados:
        (base / nombre).write_bytes(b"prueba")
    (base / "ignorado.txt").write_bytes(b"ajeno")
    hilo, cola = iniciar_escaneo([str(base)], guardar=False)
    hilo.start()
    while True:
        mensaje = cola.get(timeout=120)
        if isinstance(mensaje, tuple) and mensaje[0] == "fin":
            tipos = {r.nombre: r.tipo for r in mensaje[1]}
            assert tipos == esperados, tipos
            print(f"OK escaner: {len(esperados)} formatos con su tipo correcto (sin el .txt)")
            break
    shutil.rmtree(base, ignore_errors=True)
    print("TODO OK")


def run_reloj_roto():
    """Un stat raro (OverflowError en el 2.º archivo) NO debe matar al
    trabajador: el 3.er archivo tiene que seguir apareciendo."""
    import datetime as dt_real

    import buscador.escaner as esc

    real_datetime = dt_real.datetime

    class RelojRoto(real_datetime):
        contador = 0

        @classmethod
        def fromtimestamp(cls, t):
            cls.contador += 1
            if cls.contador == 3:  # el primer fromtimestamp del 2.º archivo
                raise OverflowError("fecha imposible")
            return real_datetime.fromtimestamp(t)

    base = Path(tempfile.mkdtemp(prefix="buscador_reloj_"))
    for nombre in ("a.docx", "b.docx", "c.docx"):
        (base / nombre).write_bytes(b"prueba")
    anterior = esc.datetime
    esc.datetime = RelojRoto
    try:
        hilo, cola = iniciar_escaneo([str(base)], guardar=False)
        hilo.start()
        while True:
            mensaje = cola.get(timeout=120)
            if isinstance(mensaje, tuple) and mensaje[0] == "fin":
                nombres = {r.nombre for r in mensaje[1]}
                assert nombres == {"a.docx", "c.docx"}, nombres
                print("OK escaner: stat imposible salta el archivo, no mata al trabajador")
                break
    finally:
        esc.datetime = anterior
        shutil.rmtree(base, ignore_errors=True)


run_reloj_roto()


run()
