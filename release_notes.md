# v1.4.0 — exportar los resultados a CSV (Ctrl+E) y Linux en cada release

## Nuevo

- 📤 **Exportar resultados a CSV con Ctrl+E:** escribe los resultados de tu
  búsqueda actual (texto escrito, filtros de tipo F2–F7, modo duplicados y
  orden vigentes) en un archivo `buscador_resultados_<fecha-hora>.csv`
  en el Escritorio. Separador `;` y UTF-8 con BOM, así que Excel lo abre
  directo. Si no hay resultados avisa y no crea el archivo.
- 🐧 **`buscador-linux-<versión>.zip` automático:** desde esta release, cada
  vez que se publica una versión GitHub Actions compila el binario para
  Ubuntu y lo adjunta a la misma release. Los usuarios de Ubuntu ya no
  necesitan instalar Python: descomprimen el zip y ejecutan `./buscador`.
- ✅ Las pruebas del programa ahora viven en el repo (`tests/`) y GitHub las
  corre en cada validación antes de compilar.

## Nota

- Los formatos con macros ya se buscaban desde v1.3.x: Word `.docm`,
  Excel `.xlsm`, PowerPoint `.pptm` (ahora con prueba del escáner).

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.4.0.zip` → contiene `buscador.exe` (doble clic y listo).
- **Ubuntu (sin instalar nada):** `buscador-linux-1.4.0.zip` → descomprimir y `./buscador`.
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).

---

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
