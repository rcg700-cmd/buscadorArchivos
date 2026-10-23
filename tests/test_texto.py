# normalizar(): minúsculas sin tildes, 1:1, longitud preservada.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_normalizar():
    from buscador.texto import normalizar

    assert normalizar("INFORMACIÓN") == "informacion"
    assert normalizar("Informe Íntimo") == "informe intimo"
    s = "áéíóúüñÁÉÍÓÚÜÑçÇgG"
    assert len(normalizar(s)) == len(s)
    assert normalizar("aäå") == "aaa"


test_normalizar()
print("OK normalizar")
