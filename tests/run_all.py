"""Corre los tests headless del repositorio, uno por proceso.

Sin pytest: cada test_*.py es un script autocontenido con la misma
estructura que venimos usando (runs de `run_test` de Textual). Uso:

    python tests/run_all.py        # desde cualquier carpeta

Termina 0 si todas pasan; 1 enumerando las fallidas.
"""
import subprocess
import sys
from pathlib import Path


def main():
    aqui = Path(__file__).resolve().parent
    pruebas = sorted(aqui.glob("test_*.py"))
    print(f"Ejecutando {len(pruebas)} prueba(s) de {aqui}")
    fallidas = []
    for p in pruebas:
        print("\n" + "=" * 70)
        print(f"==> {p.name}")
        print("=" * 70)
        resultado = subprocess.run([sys.executable, str(p)])
        if resultado.returncode != 0:
            fallidas.append(p.name)
    print("\n" + "=" * 70)
    if fallidas:
        print(f"FALLARON {len(fallidas)} de {len(pruebas)}: {', '.join(fallidas)}")
        return 1
    print(f"TODAS OK ({len(pruebas)}/{len(pruebas)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
