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


def run_sin_tildes():
    """nombre_min sale normalizado (sin tildes) y coherente entre caché v1/v2."""
    import hashlib
    import json
    import time

    import buscador.escaner as esc

    base = Path(tempfile.mkdtemp(prefix="buscador_tildes_"))
    base_cache = Path(tempfile.mkdtemp(prefix="buscador_tildes_cache_"))
    cache_original = esc._carpeta_cache
    esc._carpeta_cache = lambda: base_cache
    try:
        (base / "Informe ÍNTIMO.docx").write_bytes(b"prueba")
        hilo, cola = iniciar_escaneo([str(base)], guardar=False)
        hilo.start()
        while True:
            mensaje = cola.get(timeout=120)
            if isinstance(mensaje, tuple) and mensaje[0] == "fin":
                assert len(mensaje[1]) == 1, mensaje[1]
                assert mensaje[1][0].nombre_min == "informe intimo.docx", (
                    mensaje[1][0].nombre_min
                )
                print("OK escaner: nombre_min sin tildes (informe intimo.docx)")
                break

        # caché v2: guardar/escribir y cargar recalcula nombre_min SIEMPRE
        hilo, cola = iniciar_escaneo([str(base)], guardar=True)
        hilo.start()
        while True:
            m = cola.get(timeout=120)
            if isinstance(m, tuple) and m[0] == "fin":
                break
        clave = hashlib.sha1(repr((str(base),)).encode()).hexdigest()[:8]
        cachera = base_cache / f"cache_{clave}.json"
        for _ in range(100):
            if cachera.exists():
                break
            time.sleep(0.05)
        assert json.loads(cachera.read_text(encoding="utf-8")).get("version") == 2
        vivas = esc.cargar_cache([str(base)])
        assert vivas and vivas[0].nombre_min == "informe intimo.docx", vivas

        # caché v1 a mano (nombre_min casefold viejo): carga igual y migra
        datos = {
            "version": 1,
            "raices": [str(base)],
            "registros": [{
                "ruta": str(base / "Informe ÍNTIMO.docx"),
                "nombre": "Informe ÍNTIMO.docx",
                "tipo": "Word",
                "tamano": 4,
                "creado": "2026-01-01T00:00:00",
                "modificado": "2026-01-01T00:00:00",
                "nombre_min": "informe íntimo.docx",  # el casefold viejo, con tilde
            }],
        }
        ruta_v1 = base_cache / "cache_manual.json"
        ruta_v1.write_text(json.dumps(datos), encoding="utf-8")
        original = esc._ruta_cache
        esc._ruta_cache = lambda raices: ruta_v1
        try:
            de_v1 = esc.cargar_cache([str(base)])
        finally:
            esc._ruta_cache = original
        assert de_v1[0].nombre_min == "informe intimo.docx", de_v1[0].nombre_min
        print("OK escaner: cache v1 se carga y migrantiza (v2 escrita por invalidar)")

        # borrar_cache también se lleva los indices_*.db
        (base_cache / "indice_9462e55f.db").write_bytes(b"sqlite")
        borrado = esc.borrar_cache()
        assert borrado, "no borro nada"
        assert not (base_cache / "indice_9462e55f.db").exists()
        assert not list(base_cache.glob("cache*.json")), list(base_cache.glob("cache*.json"))
        print("OK escaner: borrar_cache limpia cache*.json y indice_*.db")
    finally:
        esc._carpeta_cache = cache_original
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(base_cache, ignore_errors=True)


run_sin_tildes()


run()
