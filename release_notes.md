# v1.0.0 — primera versión pública

Buscador de archivos de Office y PDF **por nombre**, con resultados mientras escribes. TUI en Python + Textual. Windows y Ubuntu.

## Qué incluye esta release

- ✅ Búsqueda por nombre completo o parcial, filtrando al instante (search-as-you-type)
- ✅ Escaneo **en paralelo** del disco (4.5× más rápido que en serie)
- ✅ Caché persistente del escaneo (arranque instantáneo; F5 para re-escanear)
- ✅ Resultados con: nombre, tipo, fecha de creación, fecha de modificación, peso y **carpeta**
- ✅ Columnas separadas y alineadas, orden por nombre A→Z
- ✅ Navegación con teclado (↑↓ + Enter) y ratón (doble clic) para abrir el archivo
- ✅ Esc para salir a la terminal, Ctrl+Q también
- ✅ Contador "Visibles" junto al total de encontrados

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.0.0.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
