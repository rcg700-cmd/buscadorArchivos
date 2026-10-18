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
- Ejecutar: `python -m buscador` (escanea todo el disco: todos los rígidos en Windows, `/` en Linux) o `python -m buscador "D:\Docs"` para carpetas concretas.
- Verificación rápida sin levantar la TUI: `python -c "import buscador.escaner, buscador.app"` + un escaneo de prueba recursivo sobre una carpeta pequeña con `iniciar_escaneo`.

## Arquitectura

- `buscador/escaner.py`: hilo daemon con `os.scandir` iterativo (una pila, sin recursión), filtra por extensión y llena una `queue.Queue` con `Registro` (ruta, nombre minúsculas para filtrar, tipo, tamaño, fechas); termina con un `None` de marcador.
- `buscador/app.py`: app Textual. El tick de `set_interval(0.25, ...)` drena la cola (hilo→UI en el event loop de Textual); el filtro search-as-you-type es subcadena en `nombre_min`. Renderiza máx. `MAX_MOSTRADOS = 1000` filas; reconstruye la tabla solo si cambia la firma `(texto, total, escaneando)` y conserva `cursor_row`.
- Enter/doble clic → `os.startfile` (Windows) o `xdg-open` (Linux). No existe lógica de contenido ni índices en disco.

## Quirks conocidos

- En Linux `st_ctime` no es fecha de creación real (no es legible en general); se muestra tal cual en la columna "Creado".
- Un escaneo de todo el disco puede tardar minutos la primera vez; no hay caché/índice persistente (posible mejora futura junto con ordenar resultados).

## Próximos pasos pendientes

1. Al añadir funcionalidades nuevas, actualizar este archivo con los comandos y quirks reales.
2. Posibles mejoras futuras: caché persistente del escaneo, orden por columna, búsqueda con comodines.
