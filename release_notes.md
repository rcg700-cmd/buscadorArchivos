# v1.1.2 — retoque visual completo

Sobre la base v1.1.0 (búsqueda por nombre, filtros, orden, exclusiones, caché por ámbito) se añade una pasada estética:

## Novedades

- 🎨 **Iconos y colores por tipo en la tabla:** 📝 Word azul, 📊 Excel verde, 📽️ PowerPoint naranja, 📕 PDF rojo, 🐧 LibreOffice teal. Fechas, peso y carpeta en gris tenue; el peso alineado a la derecha.
- 🔺 **Flecha de orden en el encabezado** de la columna activa (▲ ascendente, ▼ descendente), además del indicador en la barra de estado.
- 🪟 **Borde de la tabla con título** `Resultados: N` (el total visible siempre a la vista).
- 🌈 **Barra de estado a todo color:** ⏳ escaneando en amarillo —ahora informa cuántas **carpetas quedan en cola**—, 💾 caché en cian, filtros en verde, orden en magenta.
- 🌗 **Ctrl+T:** recorre los temas de colores de Textual (claros y oscuros, tokio-night, dracula…) y **recuerda tu elección entre sesiones** (preferencias.json junto a las cachés).
- ❓ **Ayuda F1 rediseñada:** tabla de atajos a dos columnas y secciones coloreadas, ahora incluye Ctrl+T.

Sin cambios en cómo escanea ni busca: solo la cara.

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.1.2.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
