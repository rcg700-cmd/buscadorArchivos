"""Interfaz TUI (Textual) del buscador de archivos de Office.

- Campo de búsqueda con filtrado incremental (search-as-you-type).
- Tabla de resultados navegable con flechas y ratón; Enter o doble clic abren
  el archivo seleccionado con la aplicación predeterminada.
"""

import os
import queue
import subprocess

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Input, Label

from .escaner import Registro, cargar_cache, iniciar_escaneo, raices_por_defecto

MAX_MOSTRADOS = 1000  # máximo de filas en pantalla (por rendimiento)


def fmt_tamano(n):
    """Tamaño en formato legible: 2,4 MB en vez de 2_689_330 bytes."""
    for unidad in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unidad == "TB":
            return f"{n} B" if unidad == "B" else f"{n:.1f} {unidad}"
        n /= 1024
    return f"{n} B"


def fmt_fecha(d):
    return d.strftime("%d/%m/%Y %H:%M")


def fmt_num(n):
    return f"{n:,}".replace(",", ".")


def _clave_orden(r):
    """Orden alfabético por nombre (insensible a mayúsculas) + ruta de desempate."""
    return (r.nombre_min, r.ruta)


def abrir_archivo(ruta):
    """Abre el archivo con la aplicación predeterminada del sistema."""
    try:
        if os.name == "nt":
            os.startfile(ruta)  # noqa: S606 — función específica de Windows
        else:
            subprocess.Popen(  # noqa: S603
                ["xdg-open", ruta],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError:
        pass


class BuscadorApp(App):
    """App principal: buscar archivos por nombre en todo el disco."""

    CSS = """
    #entrada { width: 100%; }
    #estado { width: 100%; padding: 0 1; color: $text; }
    #resultados { height: 1fr; }
    """

    BINDINGS = [Binding("f5", "reescanear", "Reescanear el disco", show=True, priority=True)]

    def __init__(self, raices=None):
        super().__init__()
        self.raices = tuple(raices) if raices else raices_por_defecto()
        self.cola = queue.Queue()  # registros que llegan del hilo de escaneo
        self.registros = []  # todos los archivos conocidos (caché + escaneo)
        self.mostradas = []  # los que pasan el filtro actual (máx. MAX_MOSTRADOS)
        self.rutas_conocidas = set()  # para no duplicar al fusionar escaneo+caché
        self.texto = ""  # filtro actual
        self.escaneando = False
        self.de_cache = False  # True mientras la vista provenga (solo) de la caché
        self._firma = None  # (texto, total, escaneando, de_cache) para saber si cambió la vista

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Escribe el nombre (o parte) del archivo…", id="entrada")
        yield Label("", id="estado")
        tabla = DataTable(id="resultados", cursor_type="row", zebra_stripes=True)
        tabla.add_columns("Nombre", "Tipo", "Creado", "Modificado", "Peso")
        yield tabla
        yield Footer()

    def on_mount(self):
        # Revisa la cola 4 veces/segundo (activa solo cuando haya escaneo)
        self.set_interval(0.25, self._recibir)
        # Si hay caché válida para estas raíces, se muestra al instante
        cache = cargar_cache(self.raices)
        if cache:
            cache.sort(key=_clave_orden)  # resultados siempre por nombre A→Z
            self.registros = cache
            self.rutas_conocidas = {r.ruta for r in cache}
            self.de_cache = True
            self._refrescar()
        else:
            self._comenzar_escaneo()

    def _comenzar_escaneo(self):
        """Inicia un escaneo en segundo plano sin borrar lo ya visible."""
        self.escaneando = True
        self.hilo, self.cola = iniciar_escaneo(self.raices)
        self.hilo.start()
        self._firma = None
        self._refrescar()

    def action_reescanear(self):
        """F5: fuerza un re-escaneo completo (actualiza la caché al terminar)."""
        if self.escaneando:
            self.notify("Ya hay un escaneo en curso", severity="warning")
            return
        self.de_cache = True
        self.notify("Reescaneando el disco… (F5). Los resultados seguirán visibles")
        self._comenzar_escaneo()

    @on(Input.Changed)
    def _cambio_texto(self, event: Input.Changed):
        self.texto = event.value
        self._refrescar()

    def _recibir(self):
        """Mueve los registros nuevos del hilo de escaneo a la lista principal.

        Si hay caché visible, se fusiona sin duplicados (por ruta); al llegar la
        señal de fin se reemplaza todo por la lista fresca del escáner.
        """
        nuevo = False
        fin = False
        while True:
            try:
                elemento = self.cola.get_nowait()
            except queue.Empty:
                break
            if isinstance(elemento, tuple) and elemento[0] == "fin":
                lista = elemento[1]
                lista.sort(key=_clave_orden)  # resultados siempre por nombre A→Z
                self.registros = lista
                self.rutas_conocidas = {r.ruta for r in self.registros}
                self.escaneando = False
                self.de_cache = False
                fin = True
                break
            r = elemento
            if r.ruta in self.rutas_conocidas:  # ya visible (vía caché o antes)
                continue
            self.rutas_conocidas.add(r.ruta)
            self.registros.append(r)
            nuevo = True
        if nuevo or fin:
            self._refrescar()

    def _encontradas(self):
        """Aplica el filtro por nombre (subcadena, sin distinguir mayúsculas)."""
        if not self.texto:
            return self.registros
        t = self.texto.casefold()
        return [r for r in self.registros if t in r.nombre_min]

    def _refrescar(self):
        """Reconstruye la tabla si el filtro o el escaneo cambiaron."""
        encontradas = self._encontradas()
        firma = (self.texto, len(encontradas), self.escaneando, self.de_cache)
        if firma == self._firma:
            return
        self._firma = firma

        tabla = self.query_one("#resultados", DataTable)
        fila_cursor = tabla.cursor_row  # para no perder la posición al rellenar
        tabla.clear()
        self.mostradas = encontradas[:MAX_MOSTRADOS]
        ocultas = len(encontradas) - len(self.mostradas)
        for i, r in enumerate(self.mostradas):
            tabla.add_row(
                (r.nombre, r.tipo, fmt_fecha(r.creado), fmt_fecha(r.modificado), fmt_tamano(r.tamano)),
                key=str(i),
            )
        try:
            tabla.move_cursor(row=fila_cursor)
        except Exception:
            pass

        estado = f"Encontrados: {fmt_num(len(self.registros))} archivos de Office/PDF"
        if ocultas > 0:
            estado += f" — mostrando las primeras {fmt_num(len(self.mostradas))} (sigue escribiendo)"
        if self.escaneando:
            estado = "⏳ Escaneando el disco… " + estado
        elif self.de_cache:
            estado = "💾 Datos de caché (F5 para reescanear). " + estado
        self.query_one("#estado", Label).update(estado)

    @on(DataTable.RowSelected)
    def _abrir_seleccion(self, event: DataTable.RowSelected):
        """Enter o doble clic sobre una fila abre el archivo."""
        try:
            i = int(event.row_key.value or "")
        except (TypeError, ValueError):
            return
        if 0 <= i < len(self.mostradas):
            abrir_archivo(self.mostradas[i].ruta)
            self.notify(f"Abriendo: {self.mostradas[i].ruta}")


def main(raices=None):
    BuscadorApp(list(raices) if raices else None).run()
