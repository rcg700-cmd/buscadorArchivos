# v1.1.0 — abrir carpeta, filtros, orden y exclusiones


Sobre la base v1.0.0 (búsqueda por nombre mientras escribes, escaneo en paralelo, caché por ámbito) se añaden:

## Novedades

- ✅ **Ctrl+O** abre la carpeta contenedora del archivo resaltado; **Ctrl+C** copia la ruta completa al portapapeles.
- ✅ **Filtros por tipo (apilables):** F2 Word · F3 Excel · F4 PowerPoint · F6 PDF · F7 LibreOffice. Se combinan con lo que escribas; la barra de estado muestra los activos.
- ✅ **Orden configurable:** F8 cicla la columna (Nombre → Modificado → Peso → Creado) y F9 alterna ascendente/descendente (la barra de estado muestra `Orden: Peso ↓`, por ejemplo).
- ✅ **Exclusiones:** archivo `excluir.txt` (junto a la caché) para que el escaneo ignore carpetas; admite subcadenas y comodines `*`/`?` (`node_modules`, `C:\Users\*\AppData\Local\Packages`). Se crea automáticamente con ejemplos comentados.
- ✅ Panel `/` de carpetas habituales, comodines en la búsqueda, F1 ayuda y barra de ruta inferior (de la v1.0.x, ahora documentadas en la ayuda F1).

## Descargas

- **Windows (sin instalar nada):** `buscador-windows-1.1.0.zip` → contiene `buscador.exe` (doble clic y listo).
- **Código fuente:** clona este repo y sigue el README (`instalar.cmd` / `instalar.sh`).

## Formatos buscados

Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF, LibreOffice (`.odt/.ods/.odp`).
