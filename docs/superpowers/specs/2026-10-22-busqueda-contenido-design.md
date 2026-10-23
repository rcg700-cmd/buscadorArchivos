# Diseño: búsqueda por contenido

Fecha: 2026-10-22 · Estado: en revisión (builder check)

## 1. Qué y para qué

Hoy el buscador (TUI Python 3.14 + Textual) encuentra archivos de suites
ofimáticas **solo por su nombre**. Este cambio añade búsqueda **por el texto
dentro de los documentos**, con decisiones ya tomadas con el usuario:

- **Un solo buscador:** el mismo cuadro de siempre; escribe y los resultados
  son la unión de coincidencias por nombre ∪ coincidencias por contenido.
  Sin teclas nuevas.
- **Índice automático en segundo plano:** el usuario eligió "lo que sea más
  rápido". El escaneo por nombre queda idéntico y sigue siendo instantáneo
  desde el arranque; el índice de contenido se construye en un hilo daemon
  que no bloquea la UI. Buscar por contenido se vuelve prácticamente
  instantáneo una vez llenado el índice.
- **Fragmento visible:** al resaltar un resultado que entró por contenido,
  debajo de la tabla se muestra el fragmento del documento donde aparece el
  texto buscado (zona donde hoy aparece la ruta completa).
- **Solo formatos modernos:** se indexa el contenido de los formatos
  modernos de Office/OpenDocument + PDF (ver §4). Los antiguos `.doc`,
  `.xls` y `.ppt` (Word/Excel/PowerPoint 97-2003) quedan fuera del índice de
  contenido **a propósito**: el usuario confirmó que casi no tiene documentos
  viejos; siguen encontrables por nombre como hoy.

## 2. Enfoques considerados (y su trade-off)

**Extracción de texto:**

- **A. Estándar + pypdf (ELEGIDA):** `.docx/.docm/.xlsx/.xlsm/.pptx/.pptm`
  y los `.odt/.ods/.odp` son **ZIP con XML adentro** → se leen con
  `zipfile` + `xml.etree.ElementTree` de la stdlib. Solo se añade `pypdf`
  para los PDF. exe: 18,7 MB → ~21-23 MB. Contras: código propio de
  lectura, más cuidadoso con archivos mal construidos.
- **B. Librerías dedicadas** (python-docx, openpyxl, odfpy, junto con
  pypdf): más robustez frente a rarezas, pero exe hacia ~30 MB y cinco
  dependencias nuevas. Descartada por peso; migrar a B a futuro por formato
  puntual no rompe nada (la interfaz de extracción queda aislada).

**Almacenamiento del índice (llamada propia):**

- **SQLite (stdlib `sqlite3`, ELEGIDO):** un archivo por ámbito
  `indice_<sha1>.db` junto a la caché `cache_<sha1>.json` (mismo patrón de
  ámbito que la caché actual). `LIKE` sobre una columna normalizada se
  resuelve rápido en C; archivo único, transaccional, sin dependencias.
- **JSON plano:** más simple pero escanearlo en cada tecla es caro con
  corpus grande y reescribirlo entero en cada actualización. Descartado.

**Cuándo indexar:** en un pase por segundo plano tras el escaneo (y en
arranques siguientes, solo lo cambiado). Indexar "en vivo" durante el
escaneo complicaría la cola hilo→UI; queda como mejora futura.

## 3. Objetivos / no-objetivos / anti-objetivos

**Objetivos**
- Escribir en el cuadro y que aparezcan también coincidencias por contenido,
  search-as-you-type, junto a las de nombre.
- Índice por ámbito, construido en segundo plano, reindexado incremental
  (compara mtime/tamaño), y persistente entre arranques.
- Fragmento visible al resaltar una coincidencia por contenido.
- Todo lo ya existente queda igual: filtros por tipo (F2-F7), orden (F8/F9),
  duplicados (F10), CSV (Ctrl+E), papelera (Ctrl+Supr), selector de usuario,
  temas, vigilancia, validación de caché.

**No-objetivos (v1)**
- `.doc`, `.xls`, `.ppt` antiguos: sin contenido (solo por nombre).
- OCR de PDFs escaneados: esos archivos no tienen texto real; quedan
  findables solo por nombre.
- Exportar CSV sin cambios (no añade columna de fragmento en v1).
- Búsqueda por contenido fuera de los formatos de §4 (`.rtf`, `.txt`, etc.,
  quedan fuera del alcance).

**Anti-objetivos (lo que rompería el diseño)**
- Que la UI se congele: ninguna operación del índice puede bloquear el
  event loop; mismo patrón de token de generación que la vigilancia.
- Engordar la caché de nombre: el índice es un archivo aparte (SQLite); los
  `Registro` del JSON actual siguen livianos.

## 4. Alcance de formatos

Todas las extensiones están dentro de la lista `EXTENSIONES` de
`buscador/escaner.py`; solo algunas son extraíbles:

| Extensión | Cómo se saca el texto | Notas |
|---|---|---|
| `.docx/.docm` | `word/document.xml`, nodos `<w:t>` | macro = mismo mecanismo |
| `.pptx/.pptm` | `ppt/slides/slide*.xml`, nodos `<a:t>` | idem |
| `.xlsx/.xlsm` | `xl/sharedStrings.xml` nodos `<t>` + cadenas inline de las hojas | valores *calculados* no (sin motor de cálculo) |
| `.odt/.ods/.odp` | `content.xml`, `itertext()` del cuerpo | |
| `.pdf` | `pypdf` `extract_text()` por página | con tope de páginas (§6) |

## 5. Modelo de datos del índice

Archivo por ámbito: `<carpeta_cache>/indice_<sha1(raices)>.db` — misma
carpeta y mismo SHA1 que la caché de hoy (helper análogo a `_ruta_cache`).

```sql
CREATE TABLE IF NOT EXISTS docs (
  ruta        TEXT PRIMARY KEY,
  mtime       REAL,      -- st_mtime al indexar
  tamano      INTEGER,   -- st_size al indexar
  texto_norm  TEXT,      -- casefold + sin acentos; para LIKE
  texto_blob  BLOB       -- texto original, zlib; para el fragmento
);
```

- **Normalización (decisión fija):** texto normalizado = `casefold()` +
  quitar acentos **preservando longitud** (tabla de traducción 1:1 para
  áéíóúàèìòùâêîôûäëïöüçñ y mayúsculas equivalentes; NO `NFD`, que cambia
  la longitud y rompería offsets). La consulta del usuario se normaliza
  igual antes de buscar.
- **Búsqueda por contenido:** `SELECT ruta FROM docs WHERE texto_norm LIKE
  '%<consulta_norm>%', LIMIT 5000`, con `%`/`_` de la consulta escapados.
  Los comodines `*`/`?` del usuario se traducen a `%`/`_` (igual que el
  fnmatch de nombre). Conexión por llamada, siempre cerrada
  (`with sqlite3.connect(...)`).
- **Fragmento:** al resaltar una entrada que entró por contenido,
  `SELECT texto_blob FROM docs WHERE ruta=?` → `zlib.decompress` → localizar
  la primera coincidencia del término (insensible a mayúsculas/acentos) y
  cortar una ventana de ~120 caracteres alrededor. Si el blob no está o el
  índice está desactualizado, mostrar vacío sin error.

## 6. Reglas de indexación

- **Qué se indexa:** solo registros con extensión extraíble (§4) que
  existan, con `st_size <= MAX_TAMANO_ARCHIVO` (100 MB por defecto) y, para
  PDF, tope de `MAX_PAGINAS_PDF` (500 páginas). Constantes de módulo.
- **Cuándo:** al recibir `("fin", lista)` de un escaneo y al cargar una
  caché con registros: una **pasada de índice** en hilo daemon:
  1. abre la SQLite del ámbito;
  2. para cada registro extraíble: si la fila existe y coinciden
     `mtime`/`tamano` → se salta; si no, extrae y `INSERT OR REPLACE`,
     con commit cada N=20 documentos;
  3. **saneo de borrados:** filas cuya ruta ya no exista en disco o ya no
     esté entre los registros del ámbito → `DELETE`.
- **Cancelación:** token `self._generacion` (ya existe) capturado al lanzar
  la pasada; si cambia (F5, cambio de ámbito) o la app termina, el hilo
  completa su documento en curso y cancela el resto — nunca escribe con un
  gen viejo. El teardown cierra la DB con limpieza.
- **Estado visible:** en la barra de estado, un segmento
  `🔎 índice: listo / indexando i/N / N sin texto` (verde listo, amarillo
  indexando — mismo tratamiento que ⏳).
- **Fallos de extracción** (PDF corrupto, protegido, XML raro): la entrada
  se salta, no detiene la pasada, no molesta con notify; contadas en el
  estado ("sin texto").

## 7. UI / integración en `app.py`

- **`_encontradas()`** (núcleo del filtrado): además del match por nombre
  de hoy, si hay texto de búsqueda incluye las rutas devueltas por la
  consulta SQLite (resultado cacheado por firma para no repetir la SELECT
  con el mismo texto). La unión se filtra después por tipos (F2-F7) y
  duplicados (F10) igual que hoy.
- **Marcado en lista:** las filas que entraron por contenido se ven igual
  que las demás (sin columnas nuevas); la señal de que vino por contenido
  es el fragmento en la zona inferior.
- **Fragmento:** nueva `Label #fragmento` (o segunda línea de `#ruta`, a
  juicio del builder) debajo de la tabla, estilo tenue (`#9099a2` como
  `ESTILO_META`), repintada en `RowHighlighted` y en cada `_refrescar`,
  con la misma tolerancia defensiva de `_actualizar_ruta`.
- **Progreso de indexación en la barra de estado** (§6), con
  `_pinta_estado` extendido (ojo con el KeyError conocido de `encontradas`).
- **CSV, orden, papelera, ayuda (F1):** sin cambios salvo documentar el
  índice en la ayuda y en LEAME/README.

## 8. Threading / cola

- Nuevos mensajes por la cola existente (hilo→UI):
  `("indice", gen, raices, hechos, total, sin_texto)` cada ~1 s y
  `("indice_fin", gen, raices)` al terminar. Mismo patrón que
  `("progreso", …)` / `("validadas", …)`.
- La SELECT de búsqueda corre en el hilo de la UI (es una consulta local
  típica <50 ms; si con corpus enormes se nota lenta, moverla a hilo con
  snapshot — decisión del builder, documentada).
- Una conexión SQLite por hilo (sqlite3 lo exige); no compartir objetos.

## 9. Pruebas headless (nuevas, en `tests/`, sin pytest)

Mismo contrato que hoy (script autocontenido, `run_all.py`, tempfile,
redirigir `_ruta_indice` y `_ruta_preferencias` a temporales).

1. **Extracción:** crear documentos mínimos reales con `zipfile` (docx,
   xlsx, pptx, odt) en un temporal; verificar el texto extraído. PDF
   pequeño: generar bytes mínimos válidos o servirlo como fixture constate.
2. **Normalizador:** acentos, mayúsculas, longitud preservada.
3. **Índice:** guarda y recupera; segunda pasada salta lo sin cambios;
   DELETE de borrados; cancelación por cambio de gen.
4. **Búsqueda integrada:** con índice sembrado, escribir en el Input y
   verificar que aparece la fila que solo coincidía por contenido; el
   fragmento se muestra al resaltar.
5. **Anti-fantasma:** borrado externo + pasada de saneo → el registro y su
   fila de índice desaparecen.

## 10. Riesgos / notas

- **OneDrive "solo en la nube":** leer el archivo lo descarga → indexar
  carpetas OneDrive tarda (esperado, como el escaneo hoy); documentar en
  LEAME/README.
- **xlsx sin valores calculados:** documentado en §4.
- **PDF escaneados:** sin texto; aparecen por nombre.
- **Peso del índice:** el texto completo puede sumar decenas/centenas de MB
  con corpus grande; `texto_blob` con zlib (~25-35 % del bruto) mitiga el
  lado del fragmento.
- **PyInstaller:** `pypdf` se arrastra solo; no hace excludes nuevos ni
  cambios al workflow.

## 11. Lo que queda al builder

- Nombres exactos de funciones/módulos nuevos (propuesta: módulo nuevo
  `buscador/indice.py` con `extraer_texto(ruta)`, `normalizar(texto)`,
  `pasada_indice(...)`, `buscar(...)`; `app.py` solo orquesta hilo + cola +
  estado + fragmento).
- Constantes finales (`MAX_TAMANO_ARCHIVO`, `MAX_PAGINAS_PDF`, límite LIKE,
  ventana del fragmento).
- Estilo del fragmento (truncamiento; resaltar el término o no).
- Conexión por llamada vs. conexión de lectura sostenida en la UI.
- CSS del nuevo label; layout exacto de la zona inferior.
