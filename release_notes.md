# v1.2.0 — modo duplicados y envío a la papelera

Sobre la base v1.1.3 (estética + caché verificada al abrir) se añaden dos funciones nuevas para lidiar con los nombres repetidos:

## Novedades

- 🔎 **F10 — Modo solo duplicados:** activa una vista en la que únicamente aparecen los archivos cuyo nombre se repite en más de una carpeta del ámbito actual (insensible a mayúsculas, con extensión: `informe.docx` ≠ `informe.pdf`).
  - Se agrupan y ordenan automáticamente A→Z, uno al lado del otro, para comparar rutas, fechas y pesos de un vistazo.
  - Se combina con lo que escribas en el buscador y con los filtros de tipo (F2–F7).
  - La barra de estado muestra el resumen: `Duplicados: 5 grupos · 12 archivos`.
  - Al desactivar, la tabla recupera el orden que tenías antes.
- 🗑️ **Ctrl+Supr — Enviar a la papelera:** envía el archivo resaltado a la papelera tras un diálogo de confirmación (el foco inicial está en "No"; un Enter accidental no borra nada; Esc cancela).
  - **Windows:** va a la Papelera de reciclaje y se puede restaurar desde ahí.
  - **Ubuntu:** usa `trash-put` (trash-cli) si está instalado; si no existe, lo borra definitivamente.
  - El archivo desaparece de la tabla al instante, sin re-escanear, y no vuelve a aparecer con resultados de caché en curso.
  - El borrado definitivo lo haces tú desde la papelera, fuera del programa — nada se elimina permanentemente desde la app.

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.2.0.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
