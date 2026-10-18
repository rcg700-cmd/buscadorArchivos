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
from textual.widgets import DataTable, Footer, Input, Label

from .escaner import Registro, iniciar_escaneo, raices_por_defecto

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

    def __init__(self, raices=None):
        super().__init__()
        self.raices = tuple(raices) if raices else raices_por_defecto()
        self.cola = queue.Queue()  # registros que llegan del hilo de escaneo
        self.registros = []  # todos los archivos encontrados
        self.mostradas = []  # los que pasan el filtro actual (máx. MAX_MOSTRADOS)
        self.texto = ""  # filtro actual
        self.escaneando = True
        self._firma = None  # (texto, total, escaneando) para saber si cambió la vista

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Escribe el nombre (o parte) del archivo…", id="entrada")
        yield Label("", id="estado")
        tabla = DataTable(id="resultados", cursor_type="row", zebra_stripes=True)
        tabla.add_columns("Nombre", "Tipo", "Creado", "Modificado", "Peso")
        yield tabla
        yield Footer()

    def on_mount(self):
        # Arranca el escaneo en segundo plano y revisa la cola 4 veces/segundo
        self.hilo, self.cola = iniciar_escaneo(self.raices)
        self.hilo.start()
        self.set_interval(0.25, self._recibir)

    @on(Input.Changed)
    def _cambio_texto(self, event: Input.Changed):
        self.texto = event.value
        self._refrescar()

    def _recibir(self):
        """Mueve los registros nuevos del hilo de escaneo a la lista principal."""
        nuevo = False
        analizando = True
        while analizando:
            try:
                r = self.cola.get_nowait()
            except queue.Empty:
                break
            if r is None:  # señal: escaneo terminado
                self.escaneando = False
                break
            self.registros.append(r)
            nuevo = True
        if nuevo or not self.escaneando:
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
        firma = (self.texto, len(encontradas), self.escaneando)
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
