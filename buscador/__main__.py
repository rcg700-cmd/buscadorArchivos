"""Punto de entrada: `python -m buscador [opciones] [carpetas...]`."""

import sys

from .app import cli

if __name__ == "__main__":
    cli()
