# AGENTS.md — buscadorArchivos

## Estado del repositorio

- **El repositorio está vacío.** No hay código, manifiestos ni configuración de build todavía. No intentes ejecutar ni detectar estructura: no existe.
- No hay stack decidido aún. **Pregunta al usuario antes de crear scaffolding.**

## Objetivo del proyecto (especificación acordada con el usuario)

Buscador de archivos de suites ofimáticas para escritorio:

- **Tipos a buscar:** Word (`.doc/.docx`), Excel (`.xls/.xlsx`), PowerPoint (`.ppt/.pptx`), PDF (`.pdf`) y formatos de otras suites de Office (p. ej. `.odt`, `.ods`, `.odp` si el usuario confirma).
- **Búsqueda:** **solo por nombre** (confirmado por el usuario el 2026-10-18). No se busca contenido de documentos → no hay que parsear los archivos; basta leer el filesystem (nombre + metadatos). Aun así debe soportar nombre completo, nombre parcial y **mientras se escribe** (search-as-you-type, filtrado incremental — no esperar a Enter).
- **Información a mostrar por resultado:** nombre, tipo, fecha de creación, fecha de modificación, tamaño (peso).
- **Visualizador de resultados:** lista navegable; el usuario debe poder **moverse (flechas) y seleccionar** ítems con teclado, además del ratón.
- **Plataformas:** Windows primero (prioridad); Linux Ubuntu si es viable. La elección de stack debe considerar portabilidad entre ambos o justificar por qué solo Windows.

## Convenciones del usuario

- Comunícate y escribe documentación/comentarios de cara al usuario **en español**.
- El usuario quiere trabajar de forma iterativa: proponer análisis + diseño, avanzar por pasos, y **preguntar cuando haya dudas** en lugar de asumir.

## Stack y comandos (implementado)

- **Stack:** Python 3.14 + [Textual](https://textual.textualize.io) (TUI única dependencia, en `requirements.txt`).
- Instalar dependencias: `python -m pip install -r requirements.txt`
- **Instalar comando global:** `instalar.cmd` (Windows, crea `%LOCALAPPDATA%\Microsoft\WindowsApps\buscador.bat` en el PATH de usuario; cuidado: dentro de un .bat generador, un `%` literal se escapa `%%`, y `%*` falla si se escribe `%%%*` — quedó documentado en el propio script) o `bash instalar.sh` (Ubuntu, crea `~/.local/bin/buscador`). Alternativa estándar: `python -m pip install -e .` (pyproject con `[project.scripts] buscador = buscador.app:main`, pero puede no quedar en PATH según la instalación de Python).
- Ejecutar: `buscador` (todo el disco: todos los rígidos en Windows, `/` en Linux) o `buscador "D:\Docs"`; equivalente: `python -m buscador`.
- **F5 dentro de la TUI:** fuerza re-escaneo completo y actualiza la caché.
- Verificación rápida sin levantar la TUI: `python -c "import buscador.escaner, buscador.app"` + un escaneo de prueba recursivo sobre una carpeta pequeña con `iniciar_escaneo`.

## Arquitectura

- `buscador/escaner.py`: **escaneo en paralelo** con `N_HILOS = max(4, min(32, cpu*4))` trabajadores que consumen una `cola_dirs`; `pendientes` (lista mutable + lock) cuenta carpetas en vuelo y los trabajadores se retiran cuando llega a 0. Un hilo coordinador traslada los `Registro` de la cola interna a la `queue.Queue` de la UI conforme llegan, y al final enfila `("fin", lista_completa)` como marcador. Beneficio medido: **4.5×** vs el escaneo en serie (90 s → 20 s en ~470 archivos del home).
- `buscador/app.py`: app Textual. El tick de `set_interval(0.25, ...)` drena la cola (hilo→UI en el event loop de Textual); el filtro search-as-you-type es subcadena en `nombre_min`. Renderiza máx. `MAX_MOSTRADOS = 1000` filas; reconstruye la tabla solo si cambia la firma `(texto, total, escaneando)` y conserva `cursor_row`. El orden **por nombre** se aplica al cargar la caché y al terminar cada escaneo (`_clave_orden` = nombre minúsculas + ruta de desempate); durante un escaneo en curso las llegadas nuevas aparecen sin orden hasta el fin. **Layout:** columnas de ancho fijo (`ANCHOS`) con separador visual `│` construido dentro de cada celda (`_celda`/`_celda_final`); los encabezados se generan con el mismo helper para que la división quede alineada. Columnas: Nombre, Tipo, Creado, Modificado, Peso y Carpeta (dirname de la ruta). Total ~130 columnas de terminal; en pantallas angostas la tabla muestra barra de desplazamiento horizontal. El "Nombre" se recorta con `…` si excede su ancho.
- Enter/doble clic → `os.startfile` (Windows) o `xdg-open` (Linux). No existe lógica de contenido ni índices en disco.
- **Caché (`escaner.py`):** al terminar un escaneo se guarda lista completa en JSON en el perfil de usuario (Windows `%LOCALAPPDATA%\buscador-archivo\cache.json`; Linux `$XDG_CACHE_HOME`/`buscador-archivo`), atómica vía `.json.tmp` + `replace`. La caché se carga en `on_mount` solo si sus raíces coinciden; durante un re-escaneo (F5) se fusiona por ruta con `rutas_conocidas` (sin duplicados) y al llegar `("fin", lista)` en la cola se reemplaza todo por la lista fresca. `iniciar_escaneo(raices, guardar=False)` no escribe caché (útil para pruebas).

## Quirks conocidos

- En Linux `st_ctime` no es fecha de creación real (no es legible en general); se muestra tal cual en la columna "Creado".
- La caché muestra el estado del último escaneo: los archivos creados/borrados desde entonces solo se reflejan tras F5. La primera vez (sin caché) el escaneo de todo el disco puede tardar minutos.
- Los placeholders de OneDrive (`st.stat()` sobre archivos "solo en la nube") son lentos; en carpetas OneDrive el escaneo tarda aunque sea paralelo. En discos HDD la aceleración paralela también es limitada (cuello de botella físico).
- El estado en pantalla distingue: ⏳ escaneando / 💾 de caché / nada = resultados frescos.

## Próximos pasos pendientes

1. Al añadir funcionalidades nuevas, actualizar este archivo con los comandos y quirks reales.
2. Posibles mejoras futuras: orden por columna/tecla (por ahora siempre por nombre), búsqueda con comodines, eliminar entradas de caché cuyos archivos ya no existan sin re-escanear (validación incremental).
