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


run()
