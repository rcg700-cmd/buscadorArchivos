# v1.3.0 — elegir a qué usuario buscar (F11)

Nueva función para equipos compartidos: ya no hace falta buscar en todo el disco si solo te interesan los archivos de una persona.

## Novedades

- 👥 **F11 — Selector de usuario:** abre un panel con:
  - `📁 Todo el disco` (comportamiento de siempre: todas las unidades / la raíz `C:\`).
  - `👥 Todos los usuarios` (escanea la carpeta que agrupa a los usuarios: `C:\Users` en Windows, `/home` en Linux).
  - `👤` cada usuario del equipo, uno por línea — el tuyo se marca con `(yo)`.
  - Hay campo de filtro: escribe parte del nombre y la lista se acorta al instante.
- 💾 **Se recuerda tu elección:** el ámbito elegido (usuario, carpeta del panel `/` o todo el disco) queda guardado y la próxima vez que abra el buscador arranca justo donde lo dejaste. Cada ámbito tiene su propia caché, así que alternar entre usuarios no obliga a re-escanear.
- ⚠️ Nota: al buscar en la carpeta de **otro** usuario, algunas subcarpetas protegidas (AppData de sistema, `NTUSER.DAT`...) se saltan por permisos de Windows — es lo esperado y el programa no se detiene por ello.

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.3.0.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
