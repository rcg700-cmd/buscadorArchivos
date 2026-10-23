"""Interfaz TUI (Textual) del buscador de archivos de Office.

- Campo de búsqueda con filtrado incremental (search-as-you-type).
- Tabla de resultados navegable con flechas y ratón; Enter o doble clic abren
  el archivo seleccionado con la aplicación predeterminada.
"""

import csv
import fnmatch
import json
import os
import queue
import re
import shutil
import sqlite3
import subprocess
import threading
from datetime import datetime
from pathlib import Path

from rich.cells import cell_len
from rich.text import Text
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Footer, Input, Label, ListItem, ListView, Static

from .escaner import Registro, borrar_cache, cargar_cache, guardar_cache, iniciar_escaneo, raices_por_defecto, validar_cache
from .indice import abrir_bd, buscar_ph, pasada_indice, ruta_indice
from .texto import normalizar

def texto_estado_indice(estado):
    """Texto de la barra de estado según la indexación de contenido.

    ("indexando", hechos, total, sin_texto) o ("listo", total, sin_texto).
    """
    if estado[0] == "indexando":
        _, hechos, total, sin_texto = estado
        texto = f"🔎 índice: {hechos}/{total}"
        if sin_texto:
            texto += f" · {sin_texto} sin texto"
        return f"[green]{texto}[/]"
    _, total, sin_texto = estado
    texto = f"🔎 índice: listo ({total})"
    if sin_texto:
        texto += f" · {sin_texto} sin texto"
    return f"[green]{texto}[/]"


MAX_MOSTRADOS = 1000  # máximo de filas en pantalla (por rendimiento)
INTERVALO_VIGILANCIA = 5  # segundos entre chequeos de que los archivos visibles siguen ahí

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


def carpeta_exportacion():
    """Carpeta donde dejar el CSV: el Escritorio si existe, si no el home."""
    hogar = Path.home()
    candidatos = (hogar / "Desktop", hogar / "OneDrive" / "Desktop", hogar)
    return next((c for c in candidatos if c.is_dir()), hogar)


def _antiformula(campo):
    """Cita con apóstrofe los valores que Excel tomaría como fórmula.

    Un archivo con nombre que empiece por '=', '+', '-' o '@' se ejecutaría
    como fórmula al abrir el CSV exportado (inyección CSV); la comillita lo
    deja como texto. Los campos controlados por el programa no se citan.
    """
    texto = str(campo)
    if texto.startswith(("=", "+", "-", "@")):
        return "'" + texto
    return texto


def exportar_csv(datos, ruta):
    """Escribe los registros en un CSV (separador ';', UTF-8 con BOM para Excel)."""
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(("Nombre", "Tipo", "Creado", "Modificado", "Peso (bytes)", "Carpeta", "Ruta completa"))
        for r in datos:
            w.writerow((
                _antiformula(r.nombre),
                r.tipo,
                fmt_fecha(r.creado),
                fmt_fecha(r.modificado),
                r.tamano,
                _antiformula(os.path.dirname(r.ruta)),
                _antiformula(r.ruta),
            ))
    return ruta


def _usuarios_del_sistema():
    """Carpetas de usuario del equipo (C:\\Users\\* en Windows, /home/* en Linux).

    Devuelve (base, usuarios): la carpeta que agrupa a todos los usuarios
    (para la opción 'Todos los usuarios') y cada carpeta de usuario que
    exista, ordenada alfabéticamente. Si no hay base (caso raro), (None, []).
    """
    try:
        base = Path.home().parent if os.name == "nt" else Path("/home")
        if not base.is_dir():
            return None, []
        usuarios = []
        saltar = {"all users", "default", "default user", "desktop.ini"}
        for ruta in base.iterdir():
            try:
                if not ruta.is_dir():
                    continue
            except OSError:
                continue  # sin permiso para ni mirar: no ofrecerla
            if ruta.name.casefold() in saltar:
                continue
            usuarios.append(ruta)
        usuarios.sort(key=lambda p: p.name.casefold())
        return base, usuarios
    except OSError:
        return None, []


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


class UsuarioScreen(CarpetaScreen):
    """Panel F11: elegir a qué usuario limitar la búsqueda (o todos, o todo el disco)."""

    def __init__(self, al_elegir):
        # No reutiliza CarpetaScreen.__init__: el panel de usuarios solo trae
        # sus opciones (las carpetas habituales están en el panel '/').
        ModalScreen.__init__(self)
        self._al_elegir = al_elegir
        self.candidatas = [(None, "📁 Todo el disco (todas las unidades / la raíz /)")]
        base, usuarios = _usuarios_del_sistema()
        if base:
            self.candidatas.append((base, f"👥 Todos los usuarios ({base})"))
        try:
            usuario_actual = Path.home().resolve()
        except OSError:
            usuario_actual = None
        for ruta in usuarios:
            try:
                es_yo = usuario_actual is not None and ruta.resolve() == usuario_actual
            except OSError:
                es_yo = False
            marca = "  (yo)" if es_yo else ""
            self.candidatas.append((ruta, f"👤 {ruta.name}{marca} — {ruta}"))


class ConfirmarScreen(ModalScreen):
    """Diálogo Sí/No para acciones destructivas (Ctrl+Supr). Esc cuenta como No."""

    CSS = """
    ConfirmarScreen { align: center middle; }
    #caja { width: 72; max-width: 95%; height: auto;
            border: round $panel; background: $surface; padding: 1 2; }
    #mensaje { margin-bottom: 1; }
    #botones { height: auto; align-horizontal: center; }
    Button { margin: 0 2; min-width: 14; }
    """

    BINDINGS = [Binding("escape", "cancelar", "No, cancelar", priority=True)]

    def __init__(self, mensaje):
        super().__init__()
        self._mensaje = mensaje

    def compose(self):
        with Vertical(id="caja"):
            yield Static(self._mensaje, id="mensaje")
            with Horizontal(id="botones"):
                yield Button("Sí, enviar", variant="error", id="si")
                yield Button("No, cancelar", variant="default", id="no")

    def on_mount(self):
        # El foco inicial va a "No": un Enter accidental no borra nada
        self.query_one("#no", Button).focus()

    @on(Button.Pressed, "#si")
    def _si(self):
        self.dismiss(True)

    @on(Button.Pressed, "#no")
    def _no_boton(self):
        self.dismiss(False)

    def action_cancelar(self):
        self.dismiss(False)


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


def _borrar_papelera_windows(ruta):
    """Envía a la Papelera de reciclaje de Windows (restaurable desde ahí).

    Usa SHFileOperationW con FOF_ALLOWUNDO. True si el sistema lo hizo bien.
    """
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", ctypes.c_uint),
            ("pFrom", ctypes.c_wchar_p),
            ("pTo", ctypes.c_wchar_p),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", ctypes.c_wchar_p),
        ]

    op = SHFILEOPSTRUCTW()
    op.wFunc = 3  # FO_DELETE
    op.pFrom = ruta + "\0"  # la API exige doble NUL al final
    # ALLOWUNDO (papelera) | NOCONFIRMATION | NOERRORUI | SILENT: la TUI ya
    # pidió confirmación y muestra los resultados ella misma.
    op.fFlags = 0x40 | 0x10 | 0x400 | 0x4
    resultado = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return resultado == 0 and not op.fAnyOperationsAborted


def _enviar_papelera(ruta):
    """Borra un archivo "suave": papelera si se puede. Devuelve (ok, en_papelera).

    - Windows: papelera de reciclaje (restaurable desde ahí).
    - Linux: `trash-put` (trash-cli) si está instalado; si no existe, borrado
      definitivo con os.unlink (comportamiento acordado con el usuario).
    """
    if os.name == "nt":
        try:
            ok = _borrar_papelera_windows(ruta)
        except (OSError, ValueError):
            # El backend de Windows falló (winerror de la API, o una ruta con
            # NUL incrustado que ctypes rechaza): no hubo papelera.
            ok = False
        return ok, ok
    exe = shutil.which("trash-put")
    if exe:
        try:
            r = subprocess.run(  # noqa: S603
                [exe, ruta],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return r.returncode == 0, True
        except OSError:
            return False, False
    try:
        os.unlink(ruta)
        return True, False
    except OSError:
        return False, False


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
        ("Ctrl+E", "Exportar los resultados filtrados a un CSV (en el Escritorio)"),
        ("Ctrl+T", "Cambiar el tema de colores (se recuerda entre sesiones)"),
        ("F2 / F3 / F4", "Filtrar: solo Word / Excel / PowerPoint"),
        ("F6 / F7", "Filtrar: solo PDF / LibreOffice (se apilan)"),
        ("F8 / F9", "Orden por columna / ascendente-descendente"),
        ("F10", "Modo solo duplicados (nombres que se repiten)"),
        ("Ctrl+U (o F12)", "Elegir el usuario a buscar (todos, uno o todo el disco)"),
        ("Ctrl+Supr", "Enviar a la papelera el archivo resaltado"),
        ("F5", "Reescanear el ámbito actual y actualizar caché"),
        ("Ctrl+D", "Borrar caché y re-escanear de cero"),
        ("Esc (en panel)", "Cerrar el panel abierto sin elegir"),
        ("Esc / Ctrl+Q", "Salir a la terminal"),
        ("F1", "Esta ayuda"),
    )

    FUNCIONES = (
        "• Busca Word (.doc/.docx/.docm), Excel (.xls/.xlsx/.xlsm),\n"
        "  PowerPoint (.ppt/.pptx/.pptm), PDF y LibreOffice (.odt/.ods/.odp)\n"
        "  [i]por nombre del archivo[/].",
        "• Escaneo en paralelo del disco con resultados en vivo; la búsqueda\n"
        "  funciona mientras escanea y verá cuántas carpetas quedan.",
        "• Caché por ámbito (disco completo y cada carpeta elegida con el panel\n"
        "  '/'): al salir y volver a entrar retoma al instante. Además, al abrir\n"
        "  la caché se verifica en segundo plano: los archivos borrados del disco\n"
        "  desaparecen de la lista sin re-escanear (F5 ve los de creación nueva).",
        "• Sin comodines busca todo lo que contenga el texto; con '\\*' o '?' el\n"
        "  texto se interpreta como patrón (como el 'dir' de CMD).",
        "• Busca también DENTRO del contenido: Word, Excel, PowerPoint y PDF\n"
        "  modernos (y LibreOffice) se indexan en segundo plano; al resaltar\n"
        "  un resultado verás el fragmento donde apareció lo que escribiste.",
        "• Los filtros de tipo (F2..F7) se combinan con lo que escribas.",
        "• F10 activa el modo 'solo duplicados': muestra los nombres que\n"
        "  se repiten en más de una carpeta, agrupados y ordenados A→Z.",
        "• Ctrl+U (o F12) elige a qué usuario limitar la búsqueda: todos\n"
        "  los usuarios, uno concreto o todo el disco. El ámbito elegido se\n"
        "  recuerda para la próxima vez que abras el buscador.",
        "• Ctrl+Supr envía el resaltado a la papelera (pregunta antes; en\n"
        "  Ubuntu sin trash-cli lo borra definitivamente). Borrar del todo\n"
        "  lo haces tú desde la papelera, fuera del programa.",
        "• Si borras archivos desde fuera del buscador (Explorador, etc.),\n"
        "  la lista se actualiza sola: cada pocos segundos se comprueban\n"
        "  los archivos visibles y los que ya no existen salen de la tabla.",
        "• Ctrl+E exporta los resultados de tu búsqueda (los que ves, con sus\n"
        "  filtros y su orden) a un CSV en el Escritorio; lo abre Excel.\n"
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
        Binding("ctrl+e", "exportar_csv", "Exportar resultados a CSV", show=True, priority=True),
        Binding("ctrl+t", "cambiar_tema", "Cambiar tema", show=True, priority=True),
        Binding("f2", "filtro_word", "Solo Word", show=False),
        Binding("f3", "filtro_excel", "Solo Excel", show=False),
        Binding("f4", "filtro_power", "Solo PowerPoint", show=False),
        Binding("f6", "filtro_pdf", "Solo PDF", show=False),
        Binding("f7", "filtro_libre", "Solo LibreOffice", show=False),
        Binding("f8", "orden_columna", "Cambiar orden", show=False),
        Binding("f9", "orden_direccion", "Asc/Desc", show=False),
        Binding("f10", "modo_duplicados", "Solo duplicados", show=True),
        Binding("ctrl+u", "elegir_usuario", "Elegir usuario", show=True, priority=True),
        Binding("f12", "elegir_usuario", show=False),  # alternativa: F11 lo captura la terminal
        Binding("ctrl+delete", "enviar_papelera", "Enviar a la papelera", show=True, priority=True),
    ]

    def __init__(self, raices=None):
        super().__init__()
        # Consulta UNA sola vez por sesión las raíces "todo el disco": en
        # Windows son ~26 os.path.exists (una por letra de unidad) y la barra
        # de estado se repinta varias veces por segundo (hot path).
        self._raices_defecto = tuple(raices_por_defecto())
        if raices:
            self.raices = tuple(raices)
        else:
            # Sin raíz pedida por terminal: recordar el último ámbito elegido
            guardadas = _cargar_preferencias().get("raices") or []
            if guardadas and all(os.path.isdir(x) for x in guardadas):
                self.raices = tuple(guardadas)
            else:
                self.raices = self._raices_defecto
        self.cola = queue.Queue()  # registros que llegan del hilo de escaneo
        self.registros = []  # todos los archivos conocidos (caché + escaneo)
        self.mostradas = []  # los que pasan el filtro actual (máx. MAX_MOSTRADOS)
        self.rutas_conocidas = set()  # para no duplicar al fusionar escaneo+caché
        self.texto = ""  # filtro actual
        self.filtros = set()  # tipos activos (F2/F3/F4/F6/F7); vacío = todos
        self.orden = ("nombre", False)  # (columna, descendente); F8/F9
        self.duplicados = False  # F10: mostrar solo nombres repetidos
        self._orden_previo = None  # orden a restaurar al apagar el modo duplicados
        self._rutas_borradas = set()  # enviados a papelera (evita que vuelvan como fantasmas)
        self._vigilando = False  # hay un chequeo de existencia de archivos visibles en vuelo
        self.escaneando = False
        self.de_cache = False  # True mientras la vista provenga (solo) de la caché
        self.panel_abierto = False  # el panel '/' está mostrándose
        self._progreso = None  # (archivos, carpetas en cola) informado por el escáner
        self._visibles_estado = (0, 0)  # (visibles, ocultas) del último refresco
        self._duplicados_info = None  # (grupos, archivos) del último refresco (modo F10)
        self._claves_columna = {}  # clave lógica -> ColumnKey del DataTable
        self._generacion = 0  # invalida resultados de hilos de fondo (validación) tras cambiar de ámbito o re-escanear
        self._cancelar_indice = threading.Event()  # corta la pasada de índice en vuelo
        self._estado_indice = None  # ("indexando", hechos, total, sin texto) / ("listo", total, sin texto)
        self._coincidencias = None  # rutas que entraron por contenido en la última búsqueda
        self._cache_busqueda = {}  # (texto normalizado, generación) -> rutas por contenido
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
        # Vigila que los archivos visibles sigan existiendo (borrados por fuera)
        self.set_interval(INTERVALO_VIGILANCIA, self._vigilar)
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
        # Cualquier pasada de índice de otro ámbito se queda colgada: se corta
        # (la lista de registros nueva es otra) y se limpia el estado visible.
        self._cancelar_indice.set()
        self._estado_indice = None
        self.raices = tuple(raices)
        self.registros = []
        self.rutas_conocidas = set()
        self.de_cache = False
        self._progreso = None
        self._generacion += 1  # invalida cualquier validación en vuelo del ámbito anterior
        cache = cargar_cache(self.raices)
        if cache:
            _ordenar(cache, self.orden)  # respeta el orden actual (F8/F9)
            self.registros = cache
            self.rutas_conocidas = {r.ruta for r in cache}
            self.de_cache = True
            self.escaneando = False
            self._firma = None
            self._refrescar()
            # Validación incremental en segundo plano: descarta los archivos
            # borrados desde el último escaneo sin re-escanear nada.
            self._iniciar_validacion(self.registros)
            # Indexación del contenido (Word/Excel/PDF/LibreOffice modernos):
            # pasa a segundo plano; actualiza la BD del índice con lo faltante.
            self._lanzar_indice()
        else:
            self._comenzar_escaneo()

    def _iniciar_validacion(self, lista):
        """Comprueba la lista de caché en un hilo y publica ("validadas", …)."""
        gen = self._generacion
        raices = self.raices

        def validar():
            vivas, expiradas = validar_cache(lista)
            self.cola.put(("validadas", gen, raices, vivas, expiradas))

        threading.Thread(target=validar, daemon=True).start()

    def _elegir_raiz(self, destino):
        """Callback de los paneles '/' (carpeta) y F11 (usuario).

        destino None = todo el disco; en otro caso, la ruta (Path) elegida.
        """
        if destino is None:
            raices = self._raices_defecto
            self.notify("Buscando en todo el disco")
        else:
            raices = (str(destino),)
            self.notify(f"Buscando en: {destino}")
        entrada = self.query_one("#entrada", Input)
        entrada.value = ""
        # El ámbito elegido (usuario incluido) se recuerda para la próxima vez;
        # "todo el disco" se guarda como None (vuelve al comportamiento por defecto)
        prefs = _cargar_preferencias()
        prefs["raices"] = None if destino is None else [str(x) for x in raices]
        _guardar_preferencias(prefs)
        self._aplicar_raices(raices)

    def action_elegir_usuario(self):
        """F11: abre el selector de usuario (todos, uno concreto o todo el disco)."""
        self.push_screen(UsuarioScreen(self._elegir_raiz))

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

    def action_exportar_csv(self):
        """Ctrl+E: exporta los resultados filtrados actuales a un CSV.

        Respeta el texto buscado, los filtros de tipo, el modo duplicados y
        el orden actual; no se limita al máximo de filas en pantalla.
        """
        datos = self._encontradas()
        if not datos:
            self.notify("No hay resultados que exportar", severity="warning")
            return
        nombre = f"buscador_resultados_{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        ruta = carpeta_exportacion() / nombre
        try:
            exportar_csv(datos, ruta)
        except OSError as e:
            self.notify(f"No se pudo exportar el CSV:\n{e}", severity="error")
            return
        self.notify(f"Exportados {fmt_num(len(datos))} resultados a:\n{ruta}")

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

    def _avisa_orden(self):
        """Aviso común de F8/F9 con la columna y la dirección actuales."""
        self.notify(f"Orden: {ETIQUETA_ORDEN[self.orden[0]]} {'↓' if self.orden[1] else '↑'}")

    def action_orden_columna(self):
        """F8: cicla la columna de orden (Nombre → Modificado → Peso → Creado)."""
        i = COLUMNAS_ORDEN.index(self.orden[0])
        self.orden = (COLUMNAS_ORDEN[(i + 1) % len(COLUMNAS_ORDEN)], self.orden[1])
        self._avisa_orden()
        self._firma = None
        self._refrescar()

    def action_orden_direccion(self):
        """F9: alterna ascendente/descendente."""
        self.orden = (self.orden[0], not self.orden[1])
        self._avisa_orden()
        self._firma = None
        self._refrescar()

    def action_modo_duplicados(self):
        """F10: activa/desactiva el modo 'solo duplicados'.

        Al activarlo se ordena por nombre para que los repetidos queden
        juntos; al desactivarlo se recupera el orden anterior.
        """
        self.duplicados = not self.duplicados
        if self.duplicados:
            self._orden_previo = self.orden
            self.orden = ("nombre", False)
            self.notify("Modo duplicados: activado")
        else:
            if self._orden_previo:
                self.orden = self._orden_previo
                self._orden_previo = None
            self.notify("Modo duplicados: desactivado")
        self._firma = None
        self._refrescar()

    def action_enviar_papelera(self):
        """Ctrl+Supr: envía a la papelera el archivo resaltado (con confirmación)."""
        r = self._seleccionada()
        if r is None:
            self.notify("Sin archivo resaltado", severity="warning")
            return
        # El callback va a push_screen, no al constructor del diálogo
        # (parámetro al_confirmar no usado: bug v1.2.0 que dejaba la lista sin actualizar)
        self.push_screen(
            ConfirmarScreen("¿Enviar a la papelera este archivo?\n" + r.ruta),
            lambda ok, reg=r: self._borrar_resaltado(reg) if ok else None,
        )

    def _borrar_resaltado(self, r):
        """Elimina el registro del disco (papelera si es posible) y de la lista."""
        ok, en_papelera = _enviar_papelera(r.ruta)
        if not ok:
            self.notify("No se pudo enviar a la papelera", severity="error")
            return
        self._rutas_borradas.add(r.ruta)
        self.registros = [x for x in self.registros if x.ruta != r.ruta]
        self.rutas_conocidas.discard(r.ruta)
        self._firma = None
        self._refrescar()
        self.notify(
            "Enviado a la papelera: " + r.nombre
            if en_papelera
            else "Borrado definitivo (no había papelera): " + r.nombre
        )

    def action_borrar_cache(self):
        """Ctrl+D: borra TODAS las cachés y escanea de cero."""
        habia = borrar_cache()
        self.notify("Caché borrada" if habia else "No había caché guardada")
        self._aplicar_raices(self.raices)

    def _comenzar_escaneo(self):
        """Inicia un escaneo en segundo plano sin borrar lo ya visible."""
        # La lista va a cambiar por completo: corta la pasada de índice en vuelo
        # (la del nuevo escaneo se lanza al llegar el "fin" con la lista fresca).
        self._cancelar_indice.set()
        self._estado_indice = None
        self.escaneando = True
        self._generacion += 1  # los resultados de validación de la caché quedan obsoletos
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

    def _lanzar_indice(self):
        """Pasada de índice en segundo plano sobre la lista actual.

        Corta la anterior (si la había), renueva la señal de cancelación y
        lanza `pasada_indice` en un hilo: ella publica "indice"/"indice_fin"
        sobre la cola con la generación y el ámbito de este arranque.
        """
        self._cancelar_indice.set()  # si había una pasada viva, se acaba
        cancelar = threading.Event()
        self._cancelar_indice = cancelar
        gen = self._generacion
        raices = self.raices
        registros = self.registros  # lista del momento (la pasada no la toca)
        self._estado_indice = ("indexando", 0, 0, 0)
        threading.Thread(
            target=pasada_indice,
            args=(raices, registros, self.cola, gen, cancelar),
            daemon=True,
            name="indice",
        ).start()

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
                    self._generacion += 1  # cualquier validación en vuelo ya no aplica a esta lista fresca
                    self._lanzar_indice()  # indexar el contenido de lo recién escaneado
                    fin = True
                    break
                if elemento[0] == "progreso":
                    self._progreso = (elemento[1], elemento[2])
                    hubo_progreso = True
                    continue
                if elemento[0] == "validadas":
                    self._aplicar_validadas(elemento)
                    continue
                if elemento[0] in ("indice", "indice_fin"):
                    # de otra generación u otro ámbito: obsoleto, se ignora
                    if elemento[1] != self._generacion or elemento[2] != self.raices:
                        continue
                    if elemento[0] == "índice" or elemento[0] == "indice":
                        self._estado_indice = (
                            "indexando", elemento[3], elemento[4], elemento[5],
                        )
                    elif self._estado_indice:
                        # los totales llegaron con el última "indice"
                        self._estado_indice = (
                            "listo", self._estado_indice[2], self._estado_indice[3],
                        )
                    else:
                        self._estado_indice = ("listo", 0, 0)
                    # solo repinta la barra (barato: no reconstruye la tabla)
                    self._pinta_estado(*self._visibles_estado)
                    continue
                if elemento[0] == "vigilancia":
                    self._aplicar_vigilancia(elemento)
                    continue
            r = elemento
            if r.ruta in self.rutas_conocidas or r.ruta in self._rutas_borradas:
                continue  # ya visible (vía caché o antes), o enviado a la papelera
            self.rutas_conocidas.add(r.ruta)
            self.registros.append(r)
            nuevo = True
        if nuevo or fin:
            self._refrescar()
        elif hubo_progreso and self.escaneando:
            # Solo la barra de estado (barato): no toca la tabla
            self._pinta_estado(*self._visibles_estado)

    def _vigilar(self):
        """Cada INTERVALO_VIGILANCIA s comprueba que los archivos visibles existan.

        Cubre los borrados hechos fuera del programa (Explorador, otro gestor,
        la papelera...) sin esperar a un F5. Solo mira las filas visibles
        (hasta MAX_MOSTRADOS) para que sea barato; los invisibles se actualizan
        al buscarlos o al re-ordenar. Un chequeo en vuelo anula el siguiente.
        """
        if self.escaneando or self._vigilando or not self.mostradas:
            return
        rutas = [r.ruta for r in self.mostradas]
        gen = self._generacion
        raices = self.raices
        self._vigilando = True

        def chequear():
            try:
                faltan = [ruta for ruta in rutas if not os.path.exists(ruta)]
            finally:
                self._vigilando = False
            if faltan:
                self.cola.put(("vigilancia", gen, raices, faltan))

        threading.Thread(target=chequear, daemon=True).start()

    def _aplicar_vigilancia(self, elemento):
        """Quita de la lista los archivos visibles borrados fuera del programa."""
        _, gen, raices, faltan = elemento
        if gen != self._generacion or raices != self.raices or self.escaneando:
            return  # resultado obsoleto o durante un re-escaneo (la lista ya es otra)
        faltan = [x for x in faltan if x not in self._rutas_borradas]
        if not faltan:
            return
        faltando = set(faltan)
        self._rutas_borradas.update(faltando)
        self.registros = [r for r in self.registros if r.ruta not in faltando]
        self.rutas_conocidas -= faltando
        self._firma = None
        self._refrescar()
        self.notify(
            f"{fmt_num(len(faltando))} archivo ya no existe: lista actualizada"
            if len(faltando) == 1
            else f"{fmt_num(len(faltando))} archivos ya no existen: lista actualizada"
        )

    def _aplicar_validadas(self, elemento):
        """Aplica el resultado de la validación incremental de la caché.

        Solo si sigue vigente: misma generación, mismo ámbito y la vista aún
        es de caché (un re-escaneo o cambio de carpeta lo descarta).
        """
        _, gen, raices, vivas, expiradas = elemento
        if gen != self._generacion or raices != self.raices or not self.de_cache:
            return  # resultado obsoleto: la lista ya se reemplazó por otra cosa
        # vivas conserva el orden de la caché (ya ordenada al cargarla);
        # además se excluyen los que el usuario envió a la papelera esta sesión
        vivas = [x for x in vivas if x.ruta not in self._rutas_borradas]
        self.registros = vivas
        self.rutas_conocidas = {r.ruta for r in vivas}
        self._firma = None
        self._refrescar()
        if expiradas:
            guardar_cache(self.raices, vivas)  # reescribe la caché sin los borrados
            self.notify(
                f"Caché: {fmt_num(expiradas)} archivo(s) ya no existen y se "
                "descartaron (F5 para ver los nuevos)"
            )

    def _rutas_por_contenido(self):
        """Rutas DEL AMBITO cuyo texto dentro coincide con lo escrito.

        Consulta el índice SQLite (si existe); cachea la SELECT por
        (texto normalizado, generación) para no repetirla con cada tecla.
        Solo devuelven valor las rutas de REGISTROS VIVOS: la SELECT nunca
        sintetiza resultados (el diseño exige Registros reales).
        """
        if not self.texto:
            self._coincidencias = None
            return set()
        clave = (normalizar(self.texto), self._generacion)
        if clave not in self._cache_busqueda:
            rutas = set()
            archivo = ruta_indice(self.raices)
            if archivo.exists():
                try:
                    bd = abrir_bd(archivo)
                    try:
                        rutas = set(buscar_ph(bd, self.texto))
                    finally:
                        bd.close()
                except sqlite3.Error:
                    rutas = set()  # índice dañado: solo queda la búsqueda por nombre
            self._cache_busqueda[clave] = rutas
        rutas = self._cache_busqueda[clave] & self.rutas_conocidas
        rutas -= self._rutas_borradas
        self._coincidencias = rutas
        return rutas

    def _encontradas(self):
        """Filtra por nombre, contenido y tipo según el estado actual.

        - Texto sin comodines ('*' o '?'): subcadena simple sobre el nombre.
        - Con comodines: patrón tipo cmd (fnmatch) sobre el nombre completo,
          p. ej. 'informe*', '*.pdf', 'plan?2026'.
        - UNION por contenido: además de lo que casa por nombre, se añaden
          al final los registros cuyo texto interno está en el índice y
          coincide con lo escrito (sin duplicar los ya puestos).
        - self.filtros: si tiene tipos, solo se conservan esos (corre DESPUÉS
          de la unión, también sobre las coincidencias por contenido).
        - self.duplicados (F10): conserva solo los nombres que aparecen 2+
          veces entre lo ya filtrado.
        - self.orden: ('nombre', False) conserva el orden base (los que entran
          por contenido van a continuación); otros criterios ordenan al vuelo.
        """
        if not self.texto:
            self._coincidencias = None
        filtradas = self.registros
        if self.texto:
            t = normalizar(self.texto)
            if "*" in t or "?" in t:
                regex = re.compile(fnmatch.translate(t))
                por_nombre = [r for r in filtradas if regex.match(r.nombre_min)]
            else:
                por_nombre = [r for r in filtradas if t in r.nombre_min]
            por_contenido = self._rutas_por_contenido()
            vistos = set()
            filtradas = []
            for r in por_nombre:
                filtradas.append(r)
                vistos.add(r.ruta)
            for r in self.registros:
                if r.ruta in por_contenido and r.ruta not in vistos:
                    filtradas.append(r)
                    vistos.add(r.ruta)
        if self.filtros:
            filtradas = [r for r in filtradas if r.tipo in self.filtros]
        if self.duplicados:
            cuenta = {}
            for r in filtradas:
                cuenta[r.nombre_min] = cuenta.get(r.nombre_min, 0) + 1
            filtradas = [r for r in filtradas if cuenta[r.nombre_min] >= 2]
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
        # Se restaura el resaltado solo si la fila sigue existiendo
        # (move_cursor lanza si el índice se sale de la tabla reconstruida)
        if 0 <= fila_cursor < len(self.mostradas):
            tabla.move_cursor(row=fila_cursor)

        # Borde de la tabla con el total visible (independiente de la barra de estado)
        titulo_borde = f"Resultados: {fmt_num(len(encontradas))}"
        if ocultas > 0:
            titulo_borde += f" · {fmt_num(len(self.mostradas))} en pantalla"
        tabla.border_title = titulo_borde

        self._visibles_estado = (len(encontradas), ocultas)
        self._duplicados_info = (
            (len({r.nombre_min for r in encontradas}), len(encontradas)) if self.duplicados else None
        )
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
        if self._estado_indice:
            estado += " · " + texto_estado_indice(self._estado_indice)
        if self.duplicados and self._duplicados_info:
            grupos, total = self._duplicados_info
            estado += f" · [cyan b]Duplicados[/]: {fmt_num(grupos)} grupos · {fmt_num(total)} archivos"
        if ocultas > 0:
            estado += f" — las primeras {fmt_num(len(self.mostradas))} (sigue escribiendo)"
        if self.escaneando:
            carpetas = self._progreso[1] if self._progreso else 0
            extra = f" — {fmt_num(carpetas)} carpetas en cola" if carpetas > 0 else ""
            estado = f"[yellow b]⏳ Escaneando…[/]{extra}. " + estado
        elif self.de_cache:
            estado = "[cyan]💾 Datos de caché[/] ([i]F5 re-escanear[/]). " + estado
        ambito = "todo el disco" if self.raices == self._raices_defecto else ", ".join(self.raices)
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


def raices_validas(args):
    """Separa las rutas pedidas por terminal entre existentes y no.

    Devuelve (validas, invalidas) conservando el orden. La CLI usa esto para
    avisar (y no escanear) carpetas inexistentes o flags desconocidos.
    """
    validas = [a for a in args if os.path.isdir(a)]
    invalidas = [a for a in args if not os.path.isdir(a)]
    return validas, invalidas


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
    validas, invalidas = raices_validas(args)
    for ruta in invalidas:
        print(f"Aviso: la carpeta no existe y se ignora: {ruta}")
    main(validas if validas else None)
