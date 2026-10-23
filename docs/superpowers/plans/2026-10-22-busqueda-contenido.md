# Plan de implementación: búsqueda por contenido

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el único cuadro de búsqueda encuentre archivos por nombre Y por el texto dentro de los documentos (índice SQLite en segundo plano), con fragmento visible al resaltar.

**Architecture:** Módulo nuevo `buscador/texto.py` (extracción + normalización, sin dependencias de DB) y `buscador/indice.py` (SQLite + pasada con pool paralelo estilo escáner + búsquedas). `app.py` solo orquesta: lanza la pasada al llegar `("fin", …)` o al cargar caché, drena los mensajes `("indice", …)` de la cola existente, y une las coincidencias de contenido a las de nombre en `_encontradas()`. La extracción usa stdlib (zipfile+ElementTree) para Office modernos y `pypdf` solo para PDF; los `.doc/.xls/.ppt` viejos NO se indexan por contenido.

**Tech Stack:** Python 3.14, Textual (ya presente), stdlib `sqlite3`/`zipfile`/`xml.etree.ElementTree`/`zlib`/`threading`, nueva dependencia única: `pypdf`.

**Spec:** `docs/superpowers/specs/2026-10-22-busqueda-contenido-design.md` (leer junto al plan; el spec es quien decide si algo aquí no queda).

## Global Constraints

- Comunicación y comentarios de cara al usuario en español.
- Última dependencia nueva permitida: `pypdf`. Nada más.
- Los `.doc`, `.xls`, `.ppt` (97-2003) quedan sin contenido por diseño (solo nombre).
- `normalizar()` debe preservar la longitud del texto (mapa 1:1 de caracteres; nunca `str.casefold()` completo ni `NFD`: cambian larguras — ß→ss, İ→i̇).
- La UI nunca se bloquea: toda la extracción (pool) y la escritura (escritor serial) viven en hilos daemon; los mensajes cruzan por la `self.cola` existente.
- Un token de cancelación (`threading.Event`) por pasada de índice; se cancela (`.set()`) en `_comenzar_escaneo` y `_aplicar_raices`.
- No tocar: workflows de CI, `buscador_exe.py`, el comando PyInstaller (pypdf se arrastra solo), el export a CSV (Ctrl+E) sin cambios.
- Pruebas: sin pytest; cada `tests/test_*.py` script autocontenido (`asyncio.run` + `run_test` de Textual cuando toque), `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`; redirigir `buscador.indice._carpeta_cache` y `buscador.app._ruta_preferencias` a `Path(tempfile.mkdtemp())` antes de cualquier uso de `guardar_cache`/índice; aserciones de rutas SIEMPRE con `os.path.join`.
- `python tests/run_all.py` (descubre `test_*.py` por glob) debe quedar verde en Windows y Linux al final de cada task.

## Review Focus

Los modos de falla que ningún test de tarea cubre y que más pueden morder a un usuario real:

1. **PDF de >500 páginas** — se espera contenido de las primeras 500 (parcial), no exclusión silenciosa. Test: `test_texto.py::test_pdf_trunca_paginas` (Task 3, rebaja `buscador.texto.MAX_PAGINAS_PDF=2` sobre un PDF de 3 páginas).
2. **Archivo con texto pero mal construido (zip corrupto / XML roto)** — se espera que la app siga andando y ese sea "sin texto", sin excepción en la UI. Test: `test_texto.py::test_corrupto_devuelve_none` (Tasks 1-3).
3. **Consulta tipo `50%` o `precio_2026` (con % o _ literales)** — se espera que sean texto literal y además sigan funcionando como comodines de NOMBRE como hoy. Test: `test_indice.py::test_escape_sql` (Task 4).
4. **Mensajes de índice obsoletos (gen/raíces cambiadas)** — se espera que se ignoren sin repintar ni estorbar. Test: `test_busqueda_contenido.py::test_mensaje_viejo_ignorado` (Task 7).
5. **Archivo de >100 MB** — se espera que NO se indexe por contenido (sigue apareciendo por nombre). Test: `test_indice.py::test_tamano_grande_omitido` (Task 5, rebaja el límite de módulo).

---

### Task 1: `buscador/texto.py` — `normalizar()`

**Files:**
- Create: `buscador/texto.py`
- Create: `tests/test_texto.py`

**Interfaces:**
- Produces: `normalizar(texto: str) -> str` — minúscula por carácter 1:1 + tildes a la base (á→a…, ñ→n, Á→a…), longitud preservada, `len(normalizar(t)) == len(t)` siempre; devuelve `""` para `str` vacía; levanta `TypeError` con no-str (para detectar errores en desarrollo).

- [ ] **Step 1: escribir la prueba fallida** en `tests/test_texto.py`:

```python
def test_normalizar():
    from buscador.texto import normalizar
    assert normalizar("INFORMACIÓN") == "informacion"
    assert normalizar("Informe Íntimo") == "informe intimo"
    s = "áéíóúüñÁÉÍÓÚÜÑçÇgG"
    assert len(normalizar(s)) == len(s)
    assert normalizar("aäå") == "aaa"
```

- [ ] **Step 2: correr** `python tests/test_texto.py` → FALLA (`ModuleNotFoundError: buscador.texto`).
- [ ] **Step 3: implementar** `normalizar` con una `_TABLA` de traducción a caracteres: dígitos y ASCII siguen; A-Z→a-z; vocales tildadas del español (áéíóúàèìòùâêîôûäëïöüçñ y sus mayúsculas)→ base en minúscula; cualquier otro carácter queda tal cual (nunca cambia longitud). Construir `_TABLA` una sola vez (dict de `str.maketrans`).
- [ ] **Step 4: correr** `python tests/test_texto.py` → PASS. Y `python tests/run_all.py` sigue verde al completo (las pruebas previas siguen pasando).
- [ ] **Step 5: commit** `git add buscador/texto.py tests/test_texto.py; git commit -m "texto: normalizar() 1:1 sin tildes"`

### Task 2: `extraer_texto` Office (ZIP+XML) en `texto.py`

**Files:**
- Modify: `buscador/texto.py`
- Modify: `tests/test_texto.py`

**Interfaces:**
- Consumes: `normalizar` (Task 1, no usada aquí, misma página de estilo).
- Produces: `EXTRACCION: set[str]` = {".docx",".docm",".pptx",".pptm",".xlsx",".xlsm",".odt",".ods",".odp"}; `extraer_texto(ruta: str) -> str | None` — None para "no soportado/corrupto/grande", `""` para "extraíble pero sin texto"; Office XML puro (el `.pdf` va aparte en Task 3). Ayudantes privados `_texto_docx(zf)`, `_texto_pptx(zf)`, `_texto_xlsx(zf)`, `_texto_odf(zf)` operando sobre un `zipfile.ZipFile` abierto.
- Detalles XML fijados: docx = `word/document.xml`, textos de nodos `e.tag.endswith("}t")` unidos sin separador + `"\n"` tras cada nodo `}p`; pptx = entradas de `zf.namelist()` que coincidan con `^(ppt/slides/slide\d+\.xml)$` ordenadas por número, nodo `}t` unido por espacio; xlsx = nodos `}t` de `xl/sharedStrings.xml` + cadenas inline de `xl/worksheets/sheet*.xml` (textos dentro de `}is`), todo unido por `"\n"`; odt/ods/odp = `content.xml`, `"".join(root.itertext())`.

- [ ] **Step 1: prueba fallida** en `tests/test_texto.py` — helper `fabrica_docx(texto, ruta)` que escribe un zip con `word/document.xml` (XML real minimo con namespace `w:`) y `fabrica_odt(texto, ruta)`; asserts: `extraer_texto(str(r)) == texto` para docx y odt; `fabrica_pptx` y `fabrica_xlsx` equivalentes (pptx con 2 slides, texto de ambas presente); `extraer_texto(ruta_de_un_.doc_ficticio) == None`; zip corrupto (bytes truncados de un docx) → `None` sin excepción.
- [ ] **Step 2: correr** → FALLA (name error).
- [ ] **Step 3: implementar** `extraer_texto` + helpers: abrir `ZipFile` en `with`; el switch por extensión de `os.path.splitext(ruta)[1].lower()`; TODAS las excepciones de lectura (BadZipFile, OSError, ET.ParseError) atrapadas → `return None`.
- [ ] **Step 4: correr** → PASS (`python tests/test_texto.py`, y `run_all.py` completo).
- [ ] **Step 5: commit** `git commit -am "texto: extraccion office zip+xml"`

### Task 3: PDF con pypdf + límites de módulo

**Files:**
- Modify: `buscador/texto.py`
- Modify: `requirements.txt` (añadir línea `pypdf`)
- Modify: `tests/test_texto.py`

**Interfaces:**
- Consumes: la firma de Task 2.
- Produces: constantes `MAX_TAMANO_ARCHIVO = 100 * 1024 * 1024`, `MAX_PAGINAS_PDF = 500`; `extraer_texto` ahora también acepta `.pdf`: check de tamaño primero (`os.path.getsize > MAX_TAMANO_ARCHIVO` → None), luego lazy `from pypdf import PdfReader`, `"\n".join(page.extract_text() or "" for page in reader.pages[:MAX_PAGINAS_PDF])`; excepciones (PyPdfError, OSError) → None.

- [ ] **Step 1: prueba fallida** — helper `fabrica_pdf(textos: list[str], ruta)` que escribe un PDF válido **a mano** (catálogo/páginas/helvetica, un `stream` por página con `(texto) Tj`, xref con offsets computados por el propio helper; sin compresión, pypdf no estricto lo lee). Asserts: texto de las 3 páginas presente; con `buscador.texto.MAX_PAGINAS_PDF = 2` (monkeypatch del módulo, restaurar al final) el texto de la página 3 NO aparece pero sí las 2 primeras; PDF truncado → None; `os.path.getsize` > límite → None (escribir un PDF pseudo gigante no: parchear `MAX_TAMANO_ARCHIVO=10` con fabrica_pdf real basta).
- [ ] **Step 2: correr** → FALLA.
- [ ] **Step 3: implementar** (rama `.pdf` en `extraer_texto` + `python -m pip install pypdf` en local para poder probar).
- [ ] **Step 4: correr** → PASS local; y CI cubrirá al hacer push (ya instalado `pypdf` por requirements.txt).
- [ ] **Step 5: commit** `git commit -am "texto: extraccion pdf con pypdf (topes de pagina y tamano)"`

### Task 4: `buscador/indice.py` — capa SQLite

**Files:**
- Create: `buscador/indice.py`
- Create: `tests/test_indice.py`

**Interfaces:**
- Consumes: de Task 2-3 (`normalizar`); de `escaner`: `from .escaner import _carpeta_cache` (REUTILIZAR así; escaner NO importa indice — no hay ciclo); Tests parchean `buscador.indice._carpeta_cache = lambda: Path(tempdir)`.
- Produces:
  - `ruta_indice(raices: tuple) -> Path` — mismo sha1 de 8 que `_ruta_cache`, archivo `indice_<clave>.db` en la carpeta de caché.
  - `abrir_bd(ruta: Path) -> sqlite3.Connection` — crea la tabla `docs`/`meta` según spec §5 si falta (tabla `meta` guarda solo `"version"` del esquema, valor `"1"`).
  - `existe_actualizada(bd, ruta: str, mtime: float, tamano: int) -> bool`
  - `guardar_doc(bd, ruta: str, mtime: float, tamano: int, texto: str)` — TEXT `texto_norm` = `normalizar(texto)`; BLOB `texto_blob` = `zlib.compress(texto)`; `INSERT OR REPLACE`. No commit aquí (lo hace el llamador).
  - `texto_de(bd, ruta: str) -> str` — `zlib.decompress`; `""` ante cualquier error/ausencia, nunca excepción.
  - `patron_sql(texto: str) -> str` — normalizar, luego `*`→`%`, `?`→`_`, escapar `\`, `%`, `_` literales con `\` (SQL `LIKE ... ESCAPE '\'`).
  - `buscar_ph(bd, texto: str, limite: int = 5000) -> list[str]` — `SELECT ruta FROM docs WHERE texto_norm LIKE ? ESCAPE '\\' LIMIT ?` (commit no necesario para SELECT).
  - `limpiar_bd(bd, rutas_validas: set[str]) -> int` — DELETE de filas cuya ruta no esté en el set; commit; devuelve cuántas.

- [ ] **Step 1: prueba fallida** en `tests/test_indice.py`: redirección de `_carpeta_cache` a temp; roundtrip `guardar_doc`/`existe_actualizada`/`texto_de` (texto con tildes: `texto_de` lo devuelve tal cual; `existe_actualizada` con mtime distinto → False). `test_escape_sql` con asserts fijados:
  ```python
  def test_escape_sql():
      guardar_doc(bd, "a.pdf", 1.0, 10, "precio 50% variado stocks 2026")
      assert buscar_ph(bd, "50%") == ["a.pdf"]          # % literal de la consulta (no comodín)
      assert buscar_ph(bd, "stocks_2026") == []          # _ literal escapado NO actúa de comodín
      assert buscar_ph(bd, "stocks?2026") == ["a.pdf"]   # ? del usuario = _ de SQL (un char)
      assert buscar_ph(bd, "precio*") == ["a.pdf"]       # * del usuario = % de SQL
  ```
- [ ] **Step 2: correr** → FALLA.
- [ ] **Step 3: implementar** (solo capa; `pasada_indice` va en Task 5).
- [ ] **Step 4: correr** → PASS (`python tests/test_indice.py` + `run_all.py`).
- [ ] **Step 5: commit** `git commit -am "indice: capa sqlite (schema, doc, patron sql, saneo)"`

### Task 5: `pasada_indice` — pool + escritor + cancelación

**Files:**
- Modify: `buscador/indice.py`
- Modify: `tests/test_indice.py`

**Interfaces:**
- Consumes: todo lo de Task 4; `from .escaner import N_HILOS` para el pool (reexport de escáner, constante `N_HILOS_INDICE` aquí para parchear en pruebas); `EXTRACCION` + `MAX_TAMANO_ARCHIVO` de texto (páginas ya dentro de extraer_texto).
- Produces:
  - `pasada_indice(raices: tuple, registros: list, cola, gen: int, cancelar: threading.Event) -> None` — BLOQUEANTE; la app la llama dentro de un `Thread(daemon=True)`. Crea su propio pool + escritor; publica sobre `cola`:
    - `("indice", gen, raices, hechos, total, sin_texto)` cada ~1 s,
    - `("indice_fin", gen, raices)` al terminar (también al cancelar).
  - Filtra: registros con extensión en `EXTRACCION | {".pdf"}`, `os.path.exists` y tamaño ≤ `MAX_TAMANO_ARCHIVO`; salta los que `existe_actualizada` (mtime/tamano igual); al final `limpiar_bd` con las rutas del `registros` entrante; cierra la BD solamente del hilo escritor.
  - Contrato de cancelación: si `cancelar.is_set()` en cualquier punto entre documento y documento, el pool deja de extraer y no se publica más progreso; se cierra la BD y se sale.

- [ ] **Step 1: prueba fallida** (`tests/test_indice.py`, segunda mitad): fabricar 3 docx con `fabrica_docx` (import desde `test_texto` vía `sys.path.insert(0, str(Path(__file__).resolve().parent))` y `from test_texto import fabrica_docx`); correr una `pasada_indice` SÍNCRONAMENTE (sin hilo, pasando un `queue.Queue()`): asserts `("indice_fin", …)` al final; `buscar_ph(bd, "prueba")` devuelve las 3; segunda pasada con los mismos registros: `hechos == 0` (incremental); reescribar uno con otro texto y mtime/tamano distintos → 1 hecho; borrar un docx del DISCO y pasar una lista de registros sin él → fila borrada (buscar_ph no lo devuelve); `test_tamano_grande_omitido`: rebajando `buscador.texto.MAX_TAMANO_ARCHIVO=100` en la prueba (restaurar después), un archivo sobre el límite no entra al pool: `total == 0` y su ruta no está en la BD; una nueva pasada con `cancelar = threading.Event()` ya pre-setado no procesa nada: no guarda y no encola mensajes de progreso.
- [ ] **Step 2: correr** → FALLA.
- [ ] **Step 3: implementar** — pool estilo escáner: cola de pendientes + contador de guardas/hilos; hilo escritor aparte drena `cola_texto` con `get(timeout=0.05)`; guarda `texto is not None`. PROGRESO con `time.monotonic` cada ≥1.0 s. Entrada completa, sin espera activa.
- [ ] **Step 4: correr** → PASS (test_indice + completo).
- [ ] **Step 5: commit** `git commit -am "indice: pasada con pool paralelo, escritor serial, cancelacion y saneo"`

### Task 6: escáner — `nombre_min` normalizado, caché v2, borrar índices

**Files:**
- Modify: `buscador/escaner.py` (líneas clave: `_ruta_cache`-vecino sin tocar; escanear→Registro; guardar_cache; cargar_cache; borrar_cache)
- Modify: `tests/test_escaner.py`

**Interfaces:**
- Consumes: `from .texto import normalizar` (Task 1). NO importa `indice`.
- Produces: `Registro.nombre_min` ahora es `normalizar(nombre)` (con extensión, como hoy); `guardar_cache` escribe `"version": 2`; `cargar_cache` acepta 1 y 2 y SIEMPRE recalcula `nombre_min = normalizar(d["nombre"])` (única fuente de verdad; migración gratis); `borrar_cache()` también elimina `indice_*.db` (el glob pasa a `("cache*.json", "indice_*.db")`).

- [ ] **Step 1: prueba fallida** — en `tests/test_escaner.py`: añadir caso de escaneo de un archivo llamado `Informe ÍNTIMO.docx` en temporal y asertar que en las encontradas existe un registro cuyo `nombre_min` es exactamente `"informe intimo.docx"` (minúsculas y sin tildes, con extensión). Parchear temporal de `_carpeta_cache` si el test toca `guardar_cache` (ya tienen patrón).
- [ ] **Step 2: correr** → FALLA (aún casefold, tildes vivas).
- [ ] **Step 3: implementar** los 4 cambios de escaner.py. Test de versiones: escribir cache v1 a mano (json con `nombre` acentado y `nombre_min` casefold viejo) → `cargar_cache` lo carga igual con nombre_min ya normalizado.
- [ ] **Step 4: correr** → PASS (todo el run_all; ojo test_duplicados si agrupa por `nombre_min`: agrupar tildado con sin-tilde es el comportamiento deseado, ajustar aserto si fallaba solo por tilde).
- [ ] **Step 5: commit** `git commit -am "escaner: nombre_min sin tildes (cache v2) y borrar_cache limpia indices"`

### Task 7: app — lanzar pasada, mensajes `("indice", …)`, barra de estado

**Files:**
- Modify: `buscador/app.py`
- Create: `tests/test_busqueda_contenido.py`

**Interfaces:**
- Consumes: `pasada_indice`, `ruta_indice` (Tasks 4-5).
- Produces (en `BuscadorApp`):
  - estado: `self._cancelar_indice: threading.Event` (renovado en cada lanzamiento), `self._estado_indice: tuple | None` con estados `("indexando", hechos, total, sin_texto)` y `("listo", total, sin_texto)`.
  - `_lanzar_indice()` — cancela la anterior, renueva Event, guarda `(gen, raices)` y lanza `Thread(daemon=True, target=pasada_indice, args=(self.raices, self.registros, self.cola, gen, self._cancelar_indice))`. Se la llama: en `_aplicar_raices` SOLO en la rama de caché cargada, y en `_recibir` al tratar `"fin"`. En `_comenzar_escaneo` y `_aplicar_raices` previo: `self._cancelar_indice.set()` y `self._estado_indice = None`.
  - `_recibir`: mensajes nuevos — `"indice"`/`"indice_fin"` (ignorarse si `elemento[1] != self._generacion or elemento[2] != self.raices`); en válidas: guardar estado y `self._pinta_estado(*self._visibles_estado)` (barato, sin tocar tabla); en `"indice_fin"` estado `("listo", total, sin_texto)` (los datos llegan del último `"indice"`).
  - `_pinta_estado`: tras la parte de Orden, si `self._estado_indice`: `estado += " · " + texto_estado_indice(self._estado_indice)`; helper de módulo `texto_estado_indice(estado) -> str`: `("indexando", i, total, s)` → `f"🔎 índice: {i}/{total}"` (más `f" · {s} sin texto"` si `s`; el builder elige verde/amarillo del markup a criterio propio) y `("listo", total, s)` → `f"🔎 índice: listo ({total})"`.
  - `AyudaScreen.FUNCIONES`: un bullet explicando que también busca (después de indexar) por el texto de dentro de Word/Excel/PDF/LibreOffice modernos, con el fragmento al resaltar.

- [ ] **Step 1: prueba fallida** (primera parte de `tests/test_busqueda_contenido.py`): sembrar cache real con `guardar_cache` (temp de `_carpeta_cache` y `_ruta_preferencias`), crear un `.docx` con `fabrica_docx` referenciado por el registro de caché, `run_test` con `_comenzar_escaneo` PARCHOCADO ANTES (`app._comenzar_escaneo = lambda: None` justo tras instanciar, quirk conocido de AGENTS)… espera activa ≤5 s a que la cola entregue `("indice_fin", …)`; assert `app._estado_indice[0] == "listo"` y el texto del `Label #estado` contiene `"índice: listo"`. Y `test_mensaje_viejo_ignorado`: encolar en `app.cola` una tupla `("indice", 999, rutas_fake, 1, 1, 0)` y asertar que `_estado_indice` no cambia.
- [ ] **Step 2: correr** → FALLA.
- [ ] **Step 3: implementar** los 4 puntos de la app (colas/estado/bullet ayuda).
- [ ] **Step 4: correr** → PASS.
- [ ] **Step 5: commit** `git commit -am "app: pasada de indice automatica y estado visible en la barra"`

### Task 8: unión nombre+contenido en `_encontradas()`

**Files:**
- Modify: `buscador/app.py`
- Modify: `tests/test_busqueda_contenido.py`

**Interfaces:**
- Consumes: Task 4 (`abrir_bd`, `patron_sql`/`buscar_ph`, `ruta_indice`) y Task 6 (nombre ya normalizado).
- Produces (Detalles app):
  - `self._coincidencias: set[str] | None` — rutas que entraron por contenido (semánticamente: se resetea a `None` cuando texto vacío o nombre-only).
  - `_rutas_por_contenido() -> set[str]`: si `not self.texto` → `set()`; abre `abrir_bd(ruta_indice(self.raices))` solo si el `.db` existe, `buscar_ph(bd, self.texto)`, intersección con `self.rutas_conocidas - self._rutas_borradas`; guarda `self._coincidencias` (solo rutas de REGISTROS VIVOS) y un caché `("s_texto_norm", self._generacion) -> set` en `self._cache_busqueda` para no repetir la SELECT con el mismo texto entre teclas; SIEMPRE cierra la conexión (`with`). Si la DB no existe → vacía.
  - En `_encontradas()`: el `t` de comparación pasa a `normalizar(self.texto)` para el nombre (comodines: `fnmatch.translate(t_norm)` sobre `r.nombre_min`, que ya es normalizado); y tras el match por nombre: `extra = self._rutas_por_contenido() - {r.ruta de las ya filtradas}`; añadir `[r for r in self.registros if r.ruta in extra]` al final; desduplicar si una ruta ya apareció.
  - El pipeline de filtros (F2-F7) y duplicados (F10) corre DESPUÉS de la unión, como hoy.
- [ ] **Step 1: prueba fallida** (2ª parte de `test_busqueda_contenido.py`): con la app headless ya de Task 7 y la DB sembrada (texto de `presupuesto especial`, NOMBRE que NO lo contiene y SÍ está en `registros`): escribir en `#entrada` `"presupuesto"` → aparece la fila; con texto `""` no aparece; con filtro F6 (solo PDF) sobre ese docx desaparece; con `presu*` como comodín sigue visible; el header `Resultados: N` de `_refrescar` cuenta la unión (assert por `_encontradas` para no depender de pintado headless).
- [ ] **Step 2: correr** → FALLA.
- [ ] **Step 3: implementar** (ojo: NO leer la DB dentro de `_refrescar` dos veces; `self._firma` ya sirve hoy para no reconstruir).
- [ ] **Step 4: correr** → PASS.
- [ ] **Step 5: commit** `git commit -am "app: union nombre+contenido con cache por tecla"`

### Task 9: fragmento debajo de la tabla

**Files:**
- Modify: `buscador/texto.py` (helper `fragmento`)
- Modify: `buscador/app.py` (Label `#fragmento`)
- Modify: `tests/test_busqueda_contenido.py`

**Interfaces:**
- Consumes: `normalizar`, `texto_de` (Task 4), `self._coincidencias` (Task 8).
- Produces:
  - `fragmento(texto: str, termino: str, ventana: int = 120) -> str` en `texto.py`: busca el primer hit de la forma de `termino` en el texto ORIGINAL vía copia normalizada (longitudes iguales ⇒ mismo índice); devuelve `"…"` + segmento de hasta `ventana` caracteres centrado ~30 antes del hit, con el hit DENTRO; `""` si no hay texto/hit.
  - `app.py`: `Label("", id="fragmento")` tras el `#ruta` (CSS: `#fragmento { width: 100%; padding: 0 4; color: $text-muted; margin-bottom: 0; }`); `_actualizar_fragmento()` en el mismo render de `_refrescar` y de `RowHighlighted`; toleran desmonte como `_actualizar_ruta` (`except Exception: pass`); consulta del BD SOLO al resaltar un registro puntual (barato); si `self._coincidencias is None` o la ruta no está → label vacío.
- [ ] **Step 1: prueba fallida**: unitaria de `fragmento("…presupuesto…")` y de app: al resaltar la fila que entró por contenido el label `#fragmento` tiene texto, y al resaltar una fila que solo coincidió por nombre está vacío.
- [ ] **Step 2: correr** → FALLA.
- [ ] **Step 3: implementar.**
- [ ] **Step 4: correr** → PASS.
- [ ] **Step 5: commit** `git commit -am "app: fragmento del documento bajo la tabla"`

### Task 10: limpieza final (Ayuda, docs, version, suite completa)

**Files:**
- Modify: `buscador/app.py` (AyudaScreen, si algo faltó), `requirements.txt`, `pyproject.toml` (versión → `1.5.0`), `README.md`, `LEAME.txt`, `AGENTS.md`

**Interfaces:** nada nuevo; es la tarea de cierre.

- [ ] **Step 1:** ayuda F1: el texto "por nombre del archivo" del bullet FUNCIONES (v1.0) se reescribe para reflejar que también busca por dentro de los formatos modernos, y que la primera indexación toma su tiempo en segundo plano. LEAME/README ganan un apartado "Búsqueda por contenido" (solo formatos modernos; sin texto: PDFs escaneados y .doc/.xls/.ppt viejos). AGENTS.md: documentar la arquitectura REAL del índice (nombres exactos de funciones, quirks de pruebas encontrados).
- [ ] **Step 2:** `pyproject.toml` versión `1.5.0` (la release se crea aparte con el usuario).
- [ ] **Step 3:** correr `python tests/run_all.py` completo → TODO verde (9 suites en Windows y así en el CI de Pruebas con el push).
- [ ] **Step 4: commit final** `git commit -am "v1.5.0: busqueda por contenido (docs y ayuda)"`.
