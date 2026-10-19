"""Interfaz TUI (Textual) del buscador de archivos de Office.

- Campo de búsqueda con filtrado incremental (search-as-you-type).
- Tabla de resultados navegable con flechas y ratón; Enter o doble clic abren
  el archivo seleccionado con la aplicación predeterminada.
"""

import fnmatch
import json
import os
import queue
import re
import subprocess
from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
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
# Ciclo de columnas con que se ordena (tecla F8) y su etiqueta en la barra de estado
COLUMNAS_ORDEN = ("nombre", "modificado", "tamano", "creado")
ETIQUETA_ORDEN = {"nombre": "Nombre", "modificado": "Modificado", "tamano": "Peso", "creado": "Creado"}

# Icono y color por tipo (colores brillantes de cada suite para fondo oscuro/claro)
ICONO_TIPO = {"Word": "📝", "Excel": "📊", "PowerPoint": "📽️", "PDF": "📕", "LibreOffice": "🐧"}
ESTILO_TIPO = {
    "Word": "bold #58a6ff",
    "Excel": "bold #3fb950",
    "PowerPoint": "bold #f0883e",
    "PDF": "bold #f85149",
    "LibreOffice": "bold #39c5cf",
}
ESTILO_META = "#9099a2"  # fechas y peso en gris tenue: el nombre es lo protagonista

# Columnas de la tabla: clave lógica, título y ancho (los encabezados se
# regeneran en _refrescar para mostrar la flecha de orden en la columna activa).
COLUMNAS = (
    ("nombre", "Nombre", ANCHOS["Nombre"]),
    ("tipo", "Tipo", ANCHOS["Tipo"]),
    ("creado", "Creado", ANCHOS["Creado"]),
    ("modificado", "Modificado", ANCHOS["Modificado"]),
    ("tamano", "Peso", ANCHOS["Peso"]),
    ("carpeta", "Carpeta", ANCHOS["Carpeta"]),
)


def _ancho(texto, n, derecha=False):
    """Ajusta `texto` a exactamente n celdas de pantalla.

    Se mide con cell_len (los iconos/emoji ocupan 2 celdas, no 1) para que los
    separadores │ queden alineados en todas las filas. Recorta con '…' o
    rellena con espacios a la derecha (o izquierda si `derecha`).
    """
    if cell_len(texto) > n:
        while texto and cell_len(texto) > max(0, n - 1):
            texto = texto[:-1]
        texto += "…"
    relleno = " " * (n - cell_len(texto))
    return relleno + texto if derecha else texto + relleno


def _celda(contenido, ancho, estilo="", derecha=False):
    """Celda de la tabla: contenido alineado con estilo Rich + separador."""
    return Text(_ancho(contenido, ancho - 2, derecha), estilo).append(SEP)


def _celda_final(contenido, ancho, estilo="", derecha=False):
    """Última columna: alineada pero sin separador (termina la fila)."""
    return Text(_ancho(contenido, ancho, derecha), estilo)


def _encabezado(titulo, ancho, flecha=""):
    """Encabezado de columna; la columna de orden activa lleva ▲/▼ al final."""
    contenido = f"{titulo} {flecha}" if flecha else titulo
    return _celda(contenido, ancho)


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


def _clave_de_orden(r, columna):
    """Clave de orden por columna; con desempate por nombre y ruta."""
    if columna == "tamano":
        return (r.tamano, r.nombre_min, r.ruta)
    if columna == "modificado":
        return (r.modificado, r.nombre_min, r.ruta)
    if columna == "creado":
        return (r.creado, r.nombre_min, r.ruta)
    return (r.nombre_min, r.ruta)


def _ordenar(lista, orden):
    """Ordena una lista de registros según orden=(columna, descendente)."""
    columna, descendente = orden
    lista.sort(key=lambda r: _clave_de_orden(r, columna), reverse=descendente)
    return lista


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


# ------------------------------------------------------------- preferencias


def _ruta_preferencias():
    """preferencias.json vive junto a las cachés (perfil de usuario)."""
    from .escaner import _carpeta_cache

    return _carpeta_cache() / "preferencias.json"


def _cargar_preferencias():
    try:
        return json.loads(_ruta_preferencias().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_preferencias(prefs):
    try:
        ruta = _ruta_preferencias()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(prefs), encoding="utf-8")
    except OSError:
        pass  # la preferencia es un extra: si falla, no interfiere


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


def abrir_con_sistema(ruta):
    """Abre un archivo o carpeta con la aplicación predeterminada del sistema."""
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

    ATAJOS = (
        ("(escribir)", "Filtra los resultados al instante mientras tecleas"),
        ("\\* / ?", "Comodines: informe\\*.docx, \\*.pdf, plan?2026"),
        ("/", "Panel de carpetas habituales (elige dónde buscar)"),
        ("↑ / ↓", "Moverse por los resultados"),
        ("Enter / doble clic", "Abrir el archivo con su aplicación"),
        ("Ctrl+O", "Abrir la carpeta contenedora del archivo resaltado"),
        ("Ctrl+C", "Copiar la ruta completa al portapapeles"),
        ("Ctrl+T", "Cambiar el tema de colores (se recuerda entre sesiones)"),
        ("F2 / F3 / F4", "Filtrar: solo Word / Excel / PowerPoint"),
        ("F6 / F7", "Filtrar: solo PDF / LibreOffice (se apilan)"),
        ("F8 / F9", "Orden por columna / ascendente-descendente"),
        ("F5", "Reescanear el ámbito actual y actualizar caché"),
        ("Ctrl+D", "Borrar caché y re-escanear de cero"),
        ("Esc (en panel)", "Cerrar el panel abierto sin elegir"),
        ("Esc / Ctrl+Q", "Salir a la terminal"),
        ("F1", "Esta ayuda"),
    )

    FUNCIONES = (
        "• Busca Word (.doc/.docx), Excel (.xls/.xlsx), PowerPoint (.ppt/.pptx),\n"
        "  PDF y LibreOffice (.odt/.ods/.odp) [i]por nombre del archivo[/].",
        "• Escaneo en paralelo del disco con resultados en vivo; la búsqueda\n"
        "  funciona mientras escanea y verá cuántas carpetas quedan.",
        "• Caché por ámbito (disco completo y cada carpeta elegida con el panel\n"
        "  '/'): al salir y volver a entrar retoma al instante.",
        "• Sin comodines busca todo lo que contenga el texto; con '\\*' o '?' el\n"
        "  texto se interpreta como patrón (como el 'dir' de CMD).",
        "• Los filtros de tipo (F2..F7) se combinan con lo que escribas.",
        "• Ctrl+T recorre los temas de colores (claros, oscuros…); se recuerda\n"
        "  entre sesiones.",
        "• Carpetas a ignorar: edita excluir.txt (junto a las cachés, carpeta\n"
        "  buscador-archivo en tu perfil de usuario); admite \\* y ?.",
        "• Cada resultado abre el archivo real; nada se descarga ni modifica.",
    )

    def compose(self):
        from rich.console import Group
        from rich.table import Table as RichTable

        tabla_atajos = RichTable(show_header=False, box=None, padding=(0, 2), pad_edge=False)
        for atajo, descripcion in self.ATAJOS:
            tabla_atajos.add_row(f"[yellow b]{atajo}[/]", descripcion)
        renderable = Group(
            "[b]Buscador de archivos de Office y PDF[/b]",
            "Busca por nombre y muestra tipo, fechas, peso y carpeta.",
            "",
            "[yellow b]ATAJOS[/]  ([i]Esc vuelve a la app[/])",
            tabla_atajos,
            "",
            "[yellow b]FUNCIONES[/]",
            "\n".join(self.FUNCIONES),
        )
        yield Static(renderable, id="ayuda", expand=True)

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
        Binding("ctrl+o", "abrir_carpeta", "Abrir carpeta del archivo", show=False, priority=True),
        Binding("ctrl+c", "copiar_ruta", "Copiar ruta", show=False, priority=True),
        Binding("ctrl+t", "cambiar_tema", "Cambiar tema", show=True, priority=True),
        Binding("f2", "filtro_word", "Solo Word", show=False),
        Binding("f3", "filtro_excel", "Solo Excel", show=False),
        Binding("f4", "filtro_power", "Solo PowerPoint", show=False),
        Binding("f6", "filtro_pdf", "Solo PDF", show=False),
        Binding("f7", "filtro_libre", "Solo LibreOffice", show=False),
        Binding("f8", "orden_columna", "Cambiar orden", show=False),
        Binding("f9", "orden_direccion", "Asc/Desc", show=False),
    ]

    def __init__(self, raices=None):
        super().__init__()
        self.raices = tuple(raices) if raices else raices_por_defecto()
        self.cola = queue.Queue()  # registros que llegan del hilo de escaneo
        self.registros = []  # todos los archivos conocidos (caché + escaneo)
        self.mostradas = []  # los que pasan el filtro actual (máx. MAX_MOSTRADOS)
        self.rutas_conocidas = set()  # para no duplicar al fusionar escaneo+caché
        self.texto = ""  # filtro actual
        self.filtros = set()  # tipos activos (F2/F3/F4/F6/F7); vacío = todos
        self.orden = ("nombre", False)  # (columna, descendente); F8/F9
        self.escaneando = False
        self.de_cache = False  # True mientras la vista provenga (solo) de la caché
        self.panel_abierto = False  # el panel '/' está mostrándose
        self._progreso = None  # (archivos, carpetas en cola) informado por el escáner
        self._visibles_estado = (0, 0)  # (visibles, ocultas) del último refresco
        self._claves_columna = {}  # clave lógica -> ColumnKey del DataTable
        self._firma = None  # (texto, total, escaneando, de_cache) para saber si cambió la vista

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Escribe el nombre… (/ carpetas · * ? patrones)", id="entrada")
        yield Label("", id="estado")
        tabla = DataTable(id="resultados", cursor_type="row", zebra_stripes=True)
        # Encabezados con las mismas medidas que las celdas: el separador '│'
        # queda alineado. La columna de orden (F8/F9) recibe su ▲/▼ en _refrescar.
        for clave, titulo, ancho in COLUMNAS:
            self._claves_columna[clave] = tabla.add_columns(
                (_encabezado(titulo, ancho), clave)
            )[0]
        tabla.border_title = "Resultados"
        yield tabla
        # Ruta completa del archivo resaltado (visible abajo, sin recortar en la tabla)
        yield Label("", id="ruta")
        yield Footer()

    def on_mount(self):
        # Tema recordado en preferencias.json (Ctrl+T lo cambia)
        tema = _cargar_preferencias().get("tema")
        if tema and tema in self.available_themes and tema != self.theme:
            self.theme = tema
        # Revisa la cola 4 veces/segundo (activa solo cuando haya escaneo)
        self.set_interval(0.25, self._recibir)
        self._aplicar_raices(self.raices)

    def action_cambiar_tema(self):
        """Ctrl+T: recorre los temas disponibles y recuerda el elegido."""
        temas = sorted(self.available_themes)
        try:
            nuevo = temas[(temas.index(self.theme) + 1) % len(temas)]
        except ValueError:
            nuevo = temas[0]
        self.theme = nuevo
        prefs = _cargar_preferencias()
        prefs["tema"] = nuevo
        _guardar_preferencias(prefs)
        self.notify(f"Tema: {nuevo}")

    def _aplicar_raices(self, raices):
        """Cambia el ámbito de búsqueda usando su caché si ya existe."""
        self.raices = tuple(raices)
        self.registros = []
        self.rutas_conocidas = set()
        self.de_cache = False
        self._progreso = None
        cache = cargar_cache(self.raices)
        if cache:
            _ordenar(cache, self.orden)  # respeta el orden actual (F8/F9)
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

    def _seleccionada(self):
        """Registro resaltado en la tabla, o None."""
        tabla = self.query_one("#resultados", DataTable)
        i = tabla.cursor_row
        if 0 <= i < len(self.mostradas):
            return self.mostradas[i]
        return None

    def action_abrir_carpeta(self):
        """Ctrl+O: abre la carpeta contenedora del archivo resaltado."""
        r = self._seleccionada()
        if r is None:
            self.notify("Sin archivo resaltado", severity="warning")
            return
        carpeta = os.path.dirname(r.ruta)
        abrir_con_sistema(carpeta)
        self.notify(f"Carpeta: {carpeta}")

    def _copiar(self, texto):
        """Copia al portapapeles (Textual y, si falla, clip.exe/xclip/xsel)."""
        try:
            self.copy_to_clipboard(texto)
            return True
        except Exception:
            pass
        try:
            if os.name == "nt":
                subprocess.run("clip", input=texto.encode("mbcs"), check=False)  # noqa: S603
                return True
            r1 = subprocess.run(  # noqa: S603
                ["xclip", "-selection", "clipboard"], input=texto.encode(), check=False
            )
            if r1.returncode == 0:
                return True
            r2 = subprocess.run(  # noqa: S603
                ["xsel", "-bi"], input=texto.encode(), check=False
            )
            return r2.returncode == 0
        except Exception:
            return False

    def action_copiar_ruta(self):
        """Ctrl+C: copia la ruta completa del archivo resaltado."""
        r = self._seleccionada()
        if r is None:
            self.notify("Sin archivo resaltado", severity="warning")
            return
        ok = self._copiar(r.ruta)
        self.notify("Ruta copiada" if ok else "No se pudo copiar la ruta")

    def _toggle_filtro(self, tipo):
        """F2/F3/F4/F6/F7: activa o desactiva el filtro de un tipo."""
        if tipo in self.filtros:
            self.filtros.discard(tipo)
        else:
            self.filtros.add(tipo)
        self.notify("Filtros: " + ("+".join(sorted(self.filtros)) if self.filtros else "ninguno"))
        self._firma = None
        self._refrescar()

    def action_filtro_word(self):
        self._toggle_filtro("Word")

    def action_filtro_excel(self):
        self._toggle_filtro("Excel")

    def action_filtro_power(self):
        self._toggle_filtro("PowerPoint")

    def action_filtro_pdf(self):
        self._toggle_filtro("PDF")

    def action_filtro_libre(self):
        self._toggle_filtro("LibreOffice")

    def action_orden_columna(self):
        """F8: cicla la columna de orden (Nombre → Modificado → Peso → Creado)."""
        i = COLUMNAS_ORDEN.index(self.orden[0])
        self.orden = (COLUMNAS_ORDEN[(i + 1) % len(COLUMNAS_ORDEN)], self.orden[1])
        self.notify(f"Orden: {ETIQUETA_ORDEN[self.orden[0]]} {'↓' if self.orden[1] else '↑'}")
        self._firma = None
        self._refrescar()

    def action_orden_direccion(self):
        """F9: alterna ascendente/descendente."""
        self.orden = (self.orden[0], not self.orden[1])
        self.notify(f"Orden: {ETIQUETA_ORDEN[self.orden[0]]} {'↓' if self.orden[1] else '↑'}")
        self._firma = None
        self._refrescar()

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
        hubo_progreso = False
        while True:
            try:
                elemento = self.cola.get_nowait()
            except queue.Empty:
                break
            if isinstance(elemento, tuple):
                if elemento[0] == "fin":
                    lista = elemento[1]
                    _ordenar(lista, self.orden)  # respeta el orden actual (F8/F9)
                    self.registros = lista
                    self.rutas_conocidas = {r.ruta for r in self.registros}
                    self.escaneando = False
                    self.de_cache = False
                    self._progreso = None
                    fin = True
                    break
                if elemento[0] == "progreso":
                    self._progreso = (elemento[1], elemento[2])
                    hubo_progreso = True
                    continue
            r = elemento
            if r.ruta in self.rutas_conocidas:  # ya visible (vía caché o antes)
                continue
            self.rutas_conocidas.add(r.ruta)
            self.registros.append(r)
            nuevo = True
        if nuevo or fin:
            self._refrescar()
        elif hubo_progreso and self.escaneando:
            # Solo la barra de estado (barato): no toca la tabla
            self._pinta_estado(*self._visibles_estado)

    def _encontradas(self):
        """Filtra por nombre y tipo según el estado actual.

        - Texto sin comodines ('*' o '?'): subcadena simple sobre el nombre.
        - Con comodines: patrón tipo cmd (fnmatch) sobre el nombre completo,
          p. ej. 'informe*', '*.pdf', 'plan?2026'.
        - self.filtros: si tiene tipos, solo se conservan esos.
        - self.orden: ('nombre', False) conserva el orden por nombre (el que
          ya trae la lista tras el escaneo/caché); otros criterios ordenan
          el resultado filtrado al vuelo.
        """
        filtradas = self.registros
        if self.texto:
            t = self.texto.casefold()
            if "*" in t or "?" in t:
                regex = re.compile(fnmatch.translate(t))
                filtradas = [r for r in filtradas if regex.match(r.nombre_min)]
            else:
                filtradas = [r for r in filtradas if t in r.nombre_min]
        if self.filtros:
            filtradas = [r for r in filtradas if r.tipo in self.filtros]
        columna, descendente = self.orden
        if columna == "nombre" and not descendente:
            return filtradas  # ya viene ordenada por nombre
        return sorted(filtradas, key=lambda r: _clave_de_orden(r, columna), reverse=descendente)

    def _refrescar(self):
        """Reconstruye la tabla si el filtro o el escaneo cambiaron."""
        encontradas = self._encontradas()
        firma = (self.texto, len(encontradas), self.escaneando, self.de_cache, tuple(sorted(self.filtros)), self.orden)
        if firma == self._firma:
            return
        self._firma = firma

        tabla = self.query_one("#resultados", DataTable)
        fila_cursor = tabla.cursor_row  # para no perder la posición al rellenar
        # Flecha de orden (▲/▼) en el encabezado de la columna activa
        flecha = "▲" if not self.orden[1] else "▼"
        for clave, titulo, ancho_col in COLUMNAS:
            tabla.columns[self._claves_columna[clave]].label = _encabezado(
                titulo, ancho_col, flecha=flecha if clave == self.orden[0] else ""
            )
        tabla.clear()
        self.mostradas = encontradas[:MAX_MOSTRADOS]
        ocultas = len(encontradas) - len(self.mostradas)
        for i, r in enumerate(self.mostradas):
            tabla.add_row(
                _celda(f"{ICONO_TIPO.get(r.tipo, '')} {r.nombre}", ANCHOS["Nombre"]),
                _celda(r.tipo, ANCHOS["Tipo"], ESTILO_TIPO.get(r.tipo, "")),
                _celda(fmt_fecha(r.creado), ANCHOS["Creado"], ESTILO_META),
                _celda(fmt_fecha(r.modificado), ANCHOS["Modificado"], ESTILO_META),
                _celda(fmt_tamano(r.tamano), ANCHOS["Peso"], ESTILO_META, derecha=True),
                _celda_final(os.path.dirname(r.ruta), ANCHOS["Carpeta"], ESTILO_META),
                key=str(i),
            )
        try:
            tabla.move_cursor(row=fila_cursor)
        except Exception:
            pass

        # Borde de la tabla con el total visible (independiente de la barra de estado)
        titulo_borde = f"Resultados: {fmt_num(len(encontradas))}"
        if ocultas > 0:
            titulo_borde += f" · {fmt_num(len(self.mostradas))} en pantalla"
        tabla.border_title = titulo_borde

        self._visibles_estado = (len(encontradas), ocultas)
        self._pinta_estado(len(encontradas), ocultas)
        self._actualizar_ruta()

    def _pinta_estado(self, n_visibles, ocultas):
        """Barra de estado a todo color: escaneo amarillo, caché cian, filtros verdes."""
        estado = f"[b]Encontrados:[/] {fmt_num(len(self.registros))} archivos de Office/PDF"
        if self.texto:
            estado += f" · Visibles: {fmt_num(n_visibles)}"
        if self.filtros:
            estado += " · [green b]Filtros: " + "+".join(sorted(self.filtros)) + "[/]"
        estado += f" · [magenta]Orden: {ETIQUETA_ORDEN[self.orden[0]]} {'↓' if self.orden[1] else '↑'}[/]"
        if ocultas > 0:
            estado += f" — las primeras {fmt_num(len(self.mostradas))} (sigue escribiendo)"
        if self.escaneando:
            carpetas = self._progreso[1] if self._progreso else 0
            extra = f" — {fmt_num(carpetas)} carpetas en cola" if carpetas > 0 else ""
            estado = f"[yellow b]⏳ Escaneando…[/]{extra}. " + estado
        elif self.de_cache:
            estado = "[cyan]💾 Datos de caché[/] ([i]F5 re-escanear[/]). " + estado
        ambito = "todo el disco" if self.raices == tuple(raices_por_defecto()) else ", ".join(self.raices)
        estado += f" · [i]Ámbito: {ambito}[/]"
        self.query_one("#estado", Label).update(estado)

    def _ruta_resaltada(self):
        """Ruta completa del archivo resaltado en la tabla ('' si no hay)."""
        tabla = self.query_one("#resultados", DataTable)
        i = tabla.cursor_row
        if 0 <= i < len(self.mostradas):
            return self.mostradas[i].ruta
        return ""

    def _actualizar_ruta(self):
        """Actualiza la barra de ruta; tolerante a widgets recién desmontados."""
        try:
            self.query_one("#ruta", Label).update(f"Ruta: {self._ruta_resaltada()}")
        except Exception:
            pass

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
            abrir_con_sistema(self.mostradas[i].ruta)
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
