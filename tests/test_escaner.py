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
    (base / "docs" / "prueba.docx").write_bytes(b"prueba")
    (base / "docs" / "notas.xlsx").write_bytes(b"prueba")
    hilo, cola = iniciar_escaneo([str(base)], guardar=False)
    hilo.start()
    while True:
        mensaje = cola.get(timeout=120)
        if isinstance(mensaje, tuple) and mensaje[0] == "fin":
            nombres = {r.nombre for r in mensaje[1]}
            assert nombres == {"prueba.docx", "notas.xlsx"}, nombres
            print("OK escaner: encontro los 2 archivos:", sorted(nombres))
            break
    shutil.rmtree(base, ignore_errors=True)
    print("TODO OK")


run()
