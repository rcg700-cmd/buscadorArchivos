"""Entry point para PyInstaller: el exe ejecuta `buscador.app.main`.

No usar `buscador/__main__.py` como entrada del exe: sus imports relativos
fallan fuera del paquete (sedocumento esto para futuras compilaciones).
"""

import sys

import buscador.app

if __name__ == "__main__":
    buscador.app.cli()
