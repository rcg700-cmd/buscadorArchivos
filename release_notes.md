# v1.1.3 — caché verificada al abrir

Sobre la base v1.1.2 (estética completa) se añade una mejora funcional de la caché:

## Novedades

- ✅ **Validación incremental de la caché:** al abrir la app (o cambiar de carpeta con `/`), en segundo plano se comprueba que cada archivo de la caché siga existiendo.
  - Los archivos **borrados** desde el último escaneo desaparecen de la lista al momento, con un aviso (`Caché: 3 archivos ya no existen y se descartaron…`), y la caché en disco se limpia también.
  - **Sin re-escanear ni retrasar el arranque**: la lista se muestra al instante y la limpieza llega después (una comprobación ligera por archivo).
  - Si mientras valida haces F5 o cambias de carpeta, ese resultado se cancela y no interfiere.
  - Los archivos **nuevos** siguen necesitando `F5` (detectarlos sin escanear es imposible).

Sin cambios en la búsqueda ni en los atajos.

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.1.3.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
