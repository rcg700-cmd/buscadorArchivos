# v1.2.1 — borrado que funciona y lista que se actualiza sola

Corrección de la v1.2.0 y una mejora aprovechando el viaje:

## Corregido

- 🐞 **Ctrl+Supr no borraba:** en v1.2.0 la confirmación con "Sí, enviar" cerraba el diálogo **sin borrar el archivo** (el código del borrado no quedaba conectado al botón). El envío a la papelera con confirmación funciona ya de verdad, probado de punta a punta con archivos reales.

## Nuevo

- ♻️ **La lista se actualiza sola:** cada 5 segundos se comprueba en segundo plano que los archivos visibles sigan existiendo. Si borras alguno **desde fuera del programa** (Explorador de archivos, papelera, otro gestor...), esa fila desaparece de la tabla al momento — sin F5 y sin re-escanear. Los avisos lo anuncian en la barra de estado.
- (Todo lo de v1.2.0 se mantiene: modo **F10 solo duplicados** y **F5 re-escaneo**, entre otras.)

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.2.1.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
