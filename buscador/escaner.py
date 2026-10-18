"""Escaneo del disco para encontrar archivos de Office (y PDF).

Busca SOLO por nombre/metadatos: recorre el sistema de archivos de forma
iterativa (con una pila, para no agotar la recursión), comprueba extensiones y
lee nombre, tipo, fechas y tamaño. No abre ni parsea los documentos.
"""

import os
import queue
import string
import threading
from dataclasses import dataclass
from datetime import datetime

# Extensiones admitidas -> nombre amigable del tipo
EXTENSIONES = {
    ".doc": "Word",
    ".docx": "Word",
    ".docm": "Word",
    ".xls": "Excel",
    ".xlsx": "Excel",
    ".xlsm": "Excel",
    ".ppt": "PowerPoint",
    ".pptx": "PowerPoint",
    ".pptm": "PowerPoint",
    ".pdf": "PDF",
    ".odt": "LibreOffice",
    ".ods": "LibreOffice",
    ".odp": "LibreOffice",
}

# Carpetas del sistema que no vale la pena recorrer
CARPETAS_IGNORADAS = {
    "$recycle.bin",
    "system volume information",
    "proc",
    "sys",
    "dev",
    "run",
}


@dataclass
class Registro:
    """Un archivo de Office encontrado en el disco."""

    ruta: str
    nombre: str
    tipo: str
    tamano: int
    creado: datetime
    modificado: datetime
    nombre_min: str  # nombre en minúsculas para filtrar rápido


def raices_por_defecto():
    """Raíces de búsqueda: todos los discos en Windows, todo "/" en Linux."""
    if os.name == "nt":
        return [f"{letra}:\\" for letra in string.ascii_uppercase if os.path.exists(f"{letra}:\\")]
    return ["/"]


def escanear(raices, cola):
    """Recorre las raíces y mete cada archivo encontrado en la cola.

    Al terminar mete None como marcador de fin. Los errores de permisos o de
    carpetas inaccesibles se ignoran silenciosamente.
    """
    for raiz in raices:
        pila = [raiz]
        while pila:
            carpeta = pila.pop()
            try:
                with os.scandir(carpeta) as entradas:
                    for entrada in entradas:
                        try:
                            if entrada.is_dir(follow_symlinks=False):
                                # Salta enlaces y carpetas del sistema
                                if entrada.is_symlink():
                                    continue
                                if entrada.name.lower() in CARPETAS_IGNORADAS:
                                    continue
                                pila.append(entrada.path)
                            else:
                                ext = os.path.splitext(entrada.name)[1].lower()
                                if ext not in EXTENSIONES:
                                    continue
                                st = entrada.stat()
                                nombre = entrada.name
                                cola.put(
                                    Registro(
                                        ruta=entrada.path,
                                        nombre=nombre,
                                        tipo=EXTENSIONES[ext],
                                        tamano=st.st_size,
                                        creado=datetime.fromtimestamp(st.st_ctime),
                                        modificado=datetime.fromtimestamp(st.st_mtime),
                                        nombre_min=nombre.casefold(),
                                    )
                                )
                        except OSError:
                            continue
            except OSError:
                continue
    cola.put(None)  # señal de fin del escaneo


def iniciar_escaneo(raices):
    """Devuelve (hilo, cola). Llamar a hilo.start() para comenzar."""
    cola = queue.Queue()
    hilo = threading.Thread(target=escanear, args=(tuple(raices), cola), daemon=True)
    return hilo, cola
