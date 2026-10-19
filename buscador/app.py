"""Interfaz TUI (Textual) del buscador de archivos de Office.

- Campo de búsqueda con filtrado incremental (search-as-you-type).
- Tabla de resultados navegable con flechas y ratón; Enter o doble clic abren
  el archivo seleccionado con la aplicación predeterminada.
"""

import fnmatch
import os
import queue
import re
import subprocess
from pathlib import Path

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Input, Label, ListItem, ListView, Static

from .escaner import Registro, borrar_cache, cargar_cache, iniciar_escaneo, raices_por_defecto

MAX_MOSTRADOS = 1000  # máximo de filas en pantalla (por rendimiento)

# Ancho final (en caracteres) de cada columna, separador incluido.
# Total ~130 columnas; en terminales angostos la tabla permite desplazamiento horizontal.
ANCHOS = {"Nombre": 30, "Tipo": 13, "Creado": 18, "Modificado": 18, "Peso": 11, "Carpeta": 40}
SEP = " │ "  # separador visual entre columnas


def _truncar(texto, n):
    """Recorta el texto a n caracteres con '…' si es más largo."""
    return texto if len(texto) <= n else texto[: max(0, n - 1)] + "…"


def _celda(contenido, ancho):
    """Celda de la tabla: texto alineado a la izquierda con separador final."""
    return _truncar(contenido, ancho - 2).ljust(ancho - 2) + SEP


def _celda_final(contenido, ancho):
    """Última columna: alineada pero sin separador (termina la fila)."""
    return _truncar(contenido, ancho).ljust(ancho)


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


def _carpetas_habituales():
    """Carpetas típicas del sistema (solo las que existen), para el panel '/'."""
    home = Path.home()
    nombres = ["Desktop", "Escritorio", "Documents", "Documentos", "Downloads",
               "Descargas", "Pictures", "Imágenes", "Music", "Música",
               "Videos", "Vídeos", "OneDrive/Documentos", "OneDrive/Documents"]
    rutas = [home / n.replace("/", os.sep) for n in nombres]
    if os.name != "nt":
        rutas = [Path("/")] + rutas
    encontradas = []
    vistas = set()
    for ruta in rutas:
        try:
            clave = str(ruta.resolve()).lower()
        except OSError:
            continue
        if ruta.exists() and ruta.is_dir() and clave not in vistas:
            vistas.add(clave)
            encontradas.append(ruta)
    return encontradas


class CarpetaScreen(ModalScreen):
    """Panel para elegir una carpeta raíz: filtrar, elegir y escanear."""

    CSS = """
    CarpetaScreen { align: center middle; }
    #caja { width: 90; max-width: 95%; height: auto; max-height: 24;
            border: round $panel; background: $surface; padding: 1 2; }
    #filtrar { margin-bottom: 1; }
    #lista { height: auto; max-height: 15; }
    """

    BINDINGS = [Binding("escape", "cancelar", "Cerrar", priority=True)]

    def __init__(self, al_elegir):
        super().__init__()
        self._al_elegir = al_elegir
        # Primer elemento: volver a buscar en todo el disco
        self.candidatas = [(None, "📁 Todo el disco (todas las unidades / la raíz /)")]
        self.candidatas += [(p, f"📁 {p}") for p in _carpetas_habituales()]

    def compose(self):
        yield Input(placeholder="Escribe para filtrar carpetas…", id="filtrar")
        yield ListView(id="lista")

    def on_mount(self):
        self._llenar()

    def _llenar(self):
        lista = self.query_one("#lista", ListView)
        lista.clear()
        texto = self.query_one("#filtrar", Input).value.casefold()
        elegidas = self.candidatas
        if texto:
            elegidas = [(d, t) for d, t in self.candidatas if texto in t.casefold()]
        for destino, etiqueta in elegidas:
            item = ListItem(Label(etiqueta))
            item.data = destino
            lista.append(item)

    @on(Input.Changed)
    def _filtra_carpetas(self, event: Input.Changed):
        self._llenar()

    @on(ListView.Selected)
    def _elige(self, event: ListView.Selected):
        self.dismiss()
        destino = getattr(event.item, "data", None)
        self._al_elegir(destino)

    def action_cancelar(self):
        self.dismiss()


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


class AyudaScreen(ModalScreen):
    """Pantalla flotante de ayuda (F1): atajos y funciones. Esc devuelve a la app."""

    CSS = """
    AyudaScreen { align: center middle; }
    #ayuda { width: 80; max-width: 95%; height: auto; max-height: 88%;
             border: round $panel; background: $surface; padding: 1 2; }
    """

    BINDINGS = [
        Binding("escape", "cerrar", "Volver a la app", show=True, priority=True),
        Binding("f1", "cerrar", show=False, priority=True),
    ]

    TEXTO = """\
[b]Buscador de archivos de Office y PDF[/b]
Busca por nombre y muestra tipo, fechas, peso y carpeta. Orden A→Z.

[yellow b]ATAJOS[/]
  (escribir)          Filtra los resultados al instante mientras tecleas
  \\* / ?              Comodines: informe\\*.docx, \\*.pdf, plan?2026
  /                   Panel de carpetas habituales (elige dónde buscar)
  ↑ / ↓               Moverse por los resultados
  Enter / doble clic  Abrir el archivo con su aplicación
  F5                  Reescanear el ámbito actual y actualizar caché
  Ctrl+D              Borrar caché y re-escanear de cero
  Esc (en panel)      Cerrar el panel abierto sin elegir
  Esc / Ctrl+Q        Salir a la terminal
  F1                  Esta ayuda

[yellow b]FUNCIONES[/]
  • Busca Word (.doc/.docx), Excel (.xls/.xlsx), PowerPoint (.ppt/.pptx), PDF
    y LibreOffice (.odt/.ods/.odp) [i]por nombre del archivo[/i].
  • Escaneo en paralelo del disco con resultados en vivo; la búsqueda
    funciona mientras escanea.
  • Caché por ámbito (disco completo y cada carpeta elegida con el panel
    '/'): al salir y volver a entrar retoma al instante.
  • Sin comodines busca todo lo que contenga el texto; con '\\*' o '?' el
    texto se interpreta como patrón (como el 'dir' de CMD).
  • Cada resultado abre el archivo real; nada se descarga ni modifica.
"""

    def compose(self):
        yield Static(self.TEXTO, id="ayuda", expand=True)

    def action_cerrar(self):
        self.dismiss()


class BuscadorApp(App):
    """App principal: buscar archivos por nombre en todo el disco."""

    CSS = """
    #entrada { width: 1fr; margin: 1 3 0 3; }
    #estado { width: 100%; padding: 0 4; margin-top: 1; color: $text-muted; }
    #resultados { height: 1fr; width: 1fr; margin: 1 3 0 3; border: round $panel; }
    #ruta { width: 100%; padding: 0 4; color: $text; margin-bottom: 0; }
    """

    BINDINGS = [
        Binding("f1", "ayuda", "Ayuda", show=True, priority=True),
        Binding("f5", "reescanear", "Reescanear el disco", show=True, priority=True),
        Binding("ctrl+d", "borrar_cache", "Borrar caché", show=True, priority=True),
        Binding("escape", "quit", "Salir a la terminal", show=True),
    ]

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
        self.panel_abierto = False  # el panel '/' está mostrándose
        self._firma = None  # (texto, total, escaneando, de_cache) para saber si cambió la vista

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Escribe el nombre… (/ carpetas · * ? patrones)", id="entrada")
        yield Label("", id="estado")
        tabla = DataTable(id="resultados", cursor_type="row", zebra_stripes=True)
        # Encabezados construidos igual que las celdas: el separador '│'
        # queda alineado entre encabezado y resultados.
        tabla.add_columns(
            _celda("Nombre", ANCHOS["Nombre"]),
            _celda("Tipo", ANCHOS["Tipo"]),
            _celda("Creado", ANCHOS["Creado"]),
            _celda("Modificado", ANCHOS["Modificado"]),
            _celda("Peso", ANCHOS["Peso"]),
            _celda_final("Carpeta", ANCHOS["Carpeta"]),
        )
        yield tabla
        # Ruta completa del archivo resaltado (visible abajo, sin recortar en la tabla)
        yield Label("", id="ruta")
        yield Footer()

    def on_mount(self):
        # Revisa la cola 4 veces/segundo (activa solo cuando haya escaneo)
        self.set_interval(0.25, self._recibir)
        self._aplicar_raices(self.raices)

    def _aplicar_raices(self, raices):
        """Cambia el ámbito de búsqueda usando su caché si ya existe."""
        self.raices = tuple(raices)
        self.registros = []
        self.rutas_conocidas = set()
        self.de_cache = False
        cache = cargar_cache(self.raices)
        if cache:
            cache.sort(key=_clave_orden)  # resultados siempre por nombre A→Z
            self.registros = cache
            self.rutas_conocidas = {r.ruta for r in cache}
            self.de_cache = True
            self.escaneando = False
            self._firma = None
            self._refrescar()
        else:
            self._comenzar_escaneo()

    def _elegir_raiz(self, destino):
        """Callback del panel '/': carpeta elegida (None = todo el disco)."""
        if destino is None:
            raices = raices_por_defecto()
            self.notify("Buscando en todo el disco")
        else:
            raices = (str(destino),)
            self.notify(f"Buscando en: {destino}")
        entrada = self.query_one("#entrada", Input)
        entrada.value = ""
        self._aplicar_raices(raices)

    def action_ayuda(self):
        """F1: muestra la ayuda (si no está ya abierta)."""
        if isinstance(self.screen, AyudaScreen):
            return
        self.push_screen(AyudaScreen())

    def action_borrar_cache(self):
        """Ctrl+D: borra TODAS las cachés y escanea de cero."""
        habia = borrar_cache()
        self.notify("Caché borrada" if habia else "No había caché guardada")
        self._aplicar_raices(self.raices)

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
        # Solo escucha el campo principal, no el Input del panel de carpetas
        if getattr(event.input, "id", None) != "entrada":
            return
        self.texto = event.value
        # Trigger del panel de carpetas: escribir '/' solo
        if event.value == "/" and not self.panel_abierto:
            self.panel_abierto = True
            self.push_screen(CarpetaScreen(self._elegir_raiz), self._cierra_panel)
            return
        self._refrescar()

    def _cierra_panel(self, _resultado=None):
        self.panel_abierto = False

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
        """Filtra por nombre según el texto actual.

        Sin comodines ('*' o '?'): subcadena simple (case del texto).
        Con comodines: patrón tipo cmd (fnmatch) sobre el nombre completo,
        p. ej. 'informe*', '*.pdf', 'plan?2026'.
        """
        if not self.texto:
            return self.registros
        t = self.texto.casefold()
        if "*" in t or "?" in t:
            regex = re.compile(fnmatch.translate(t))
            return [r for r in self.registros if regex.match(r.nombre_min)]
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
                _celda(r.nombre, ANCHOS["Nombre"]),
                _celda(r.tipo, ANCHOS["Tipo"]),
                _celda(fmt_fecha(r.creado), ANCHOS["Creado"]),
                _celda(fmt_fecha(r.modificado), ANCHOS["Modificado"]),
                _celda(fmt_tamano(r.tamano), ANCHOS["Peso"]),
                _celda_final(os.path.dirname(r.ruta), ANCHOS["Carpeta"]),
                key=str(i),
            )
        try:
            tabla.move_cursor(row=fila_cursor)
        except Exception:
            pass

        estado = f"Encontrados: {fmt_num(len(self.registros))} archivos de Office/PDF"
        if self.texto:
            estado += f" · Visibles: {fmt_num(len(encontradas))}"
        if ocultas > 0:
            estado += f" — las primeras {fmt_num(len(self.mostradas))} (sigue escribiendo)"
        if self.escaneando:
            estado = "⏳ Escaneando… " + estado
        elif self.de_cache:
            estado = "💾 Datos de caché (F5 re-escanear). " + estado
        ambito = "todo el disco" if self.raices == tuple(raices_por_defecto()) else ", ".join(self.raices)
        estado += f" · Ámbito: {ambito}"
        self.query_one("#estado", Label).update(estado)
        self._actualizar_ruta()

    def _ruta_resaltada(self):
        """Ruta completa del archivo resaltado en la tabla ('' si no hay)."""
        tabla = self.query_one("#resultados", DataTable)
        i = tabla.cursor_row
        if 0 <= i < len(self.mostradas):
            return self.mostradas[i].ruta
        return ""

    def _actualizar_ruta(self):
        self.query_one("#ruta", Label).update(f"Ruta: {self._ruta_resaltada()}")

    @on(DataTable.RowHighlighted)
    def _fila_resaltada(self, event: DataTable.RowHighlighted):
        self._actualizar_ruta()

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


def cli(argv=None):
    """Entrada de comandos compartida por `python -m buscador` y el exe.

    Opciones:
      --borrar-cache   borra todas las cachés antes de arrancar el escaneo.
    Resto de argumentos: rutas concretas para escanear.
    """
    import sys

    from .escaner import borrar_cache

    args = list(argv) if argv is not None else list(sys.argv[1:])
    if "--borrar-cache" in args:
        args.remove("--borrar-cache")
        print("Caché borrada." if borrar_cache() else "No había caché guardada.")
    main(args if args else None)
