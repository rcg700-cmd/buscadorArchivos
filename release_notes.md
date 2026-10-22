# v1.3.1 — el selector de usuario por fin se abre (Ctrl+U)

Corrección inmediata a la v1.3.0 para terminar de hacer usable el selector de usuario:

## Corregido

- 🐞 **F11 no llegaba al programa:** Windows Terminal y la consola clásica de Windows capturan la tecla F11 (pantalla completa), así que el panel de usuarios ni siquiera se abría. Ahora el selector es:
  - ⌨️ **Ctrl+U** (de *Usuarios*) — el atajo principal, siempre llega.
  - **F12** — alternativa, también disponible.
- Todo lo demás queda igual: lista con `📁 Todo el disco`, `👥 Todos los usuarios` y `👤` cada usuario (marcado `(yo)` el actual), campo de filtro, y el ámbito recordado entre sesiones.

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.3.1.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
