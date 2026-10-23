# La línea de comandos valida las rutas: las inexistentes se avisan y se
# ignoran, en vez de escanearlas en silencio (y repetir ese escaneo vacío
# en cada arranque).
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from buscador.app import raices_validas

tmp = Path(tempfile.mkdtemp(prefix="buscador_cli_"))
doc = tmp / "Docs"
doc.mkdir()


def main():
    # existe / no existe / un flag desconocido: las dos últimas van a invalidas
    validas, invalidas = raices_validas([str(doc), str(tmp / "Nada"), "--raro"])
    assert validas == [str(doc)], validas
    assert invalidas == [str(tmp / "Nada"), "--raro"], invalidas
    # sin argumentos: nada que validar
    assert raices_validas([]) == ([], [])
    # el orden de entrada se conserva
    validas, invalidas = raices_validas([str(tmp / "X1"), str(tmp / "X2"), str(doc)])
    assert invalidas == [str(tmp / "X1"), str(tmp / "X2")], invalidas
    assert validas == [str(doc)], validas
    print("OK raices_validas: separa existentes de inexistentes/flags, en orden")


main()
