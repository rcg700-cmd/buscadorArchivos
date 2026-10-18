"""Punto de entrada: `python -m buscador [carpetas...]`.

Sin argumentos busca en todo el disco; con argumentos solo en esas carpetas.
"""

import sys

from .app import main

if __name__ == "__main__":
    main(sys.argv[1:])
