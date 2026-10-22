# buscadorArchivos

Buscador de archivos de Office y PDF **por nombre**, con resultados **mientras escribes**. Interfaz de terminal (TUI) ligera hecha en Python + [Textual](https://textual.textualize.io). Funciona en **Windows** y **Ubuntu**.

![Vista previa](docs/vista_previa.svg)

## Características

- 🔍 Búsqueda por nombre completo o parcial, filtrando al instante mientras tecleas. Además acepta **comodines** estilo terminal: `informe*2026`, `*.pdf`, `plan?2026`.
- 📂 **Panel `/`:** escribe `/` en la búsqueda y se despliega la lista de carpetas habituales (Documentos, Descargas, Escritorio, OneDrive…). Elige una y se escanea **solo esa carpeta** (con su propia caché, así alternar no fuerza re-escanear el disco). Sin `/`, busca en todo el disco.
- 🚫 **Exclusiones:** archivo `excluir.txt` con carpetas a ignorar durante el escaneo (`node_modules`, respaldo de aplicaciones, etc.).
- 🧹 **Ctrl+D** borra las cachés y re-escanea de cero (también disponible: `buscador --borrar-cache`).
- 📄 Busca Word (`.doc/.docx/.docm`), Excel (`.xls/.xlsx/.xlsm`), PowerPoint (`.ppt/.pptx/.pptm`), PDF y **LibreOffice** (`.odt/.ods/.odp`).
- 📊 Cada resultado muestra: **nombre, tipo, fecha de creación, fecha de modificación y peso**.
- 🔎 **Modo solo duplicados:** con `F10` la tabla muestra únicamente los archivos cuyo nombre se repite en más de una carpeta (agrupados A→Z), ideal para localizar y quitar copias de sobra.
- 🗑️ **Ctrl+Supr** envía el archivo resaltado a la **papelera de reciclaje** (con confirmación). En Ubuntu sin `trash-cli` lo borra definitivamente. El borrado permanente lo haces tú desde la papelera.
- 🎨 **Nueva interfaz:** cada tipo de archivo lleva **icono y color propios** (Word azul, Excel verde, PowerPoint naranja, PDF rojo, LibreOffice teal) y el orden activo se ve con una **flecha ▲/▼ en el encabezado** de la columna. Durante el escaneo se ve cuántas carpetas quedan en cola.
- 🎯 Orden **por nombre (A→Z) por defecto** y configurable con `F8`/`F9` (peso, fechas…); lista navegable con **flechas y ratón**; `Enter` o doble clic abre el archivo con su aplicación predeterminada.
- 🌗 **Ctrl+T** recorre los temas de colores disponibles (claros y oscuros); la preferencia se recuerda entre sesiones.
- 💾 **Caché del escaneo**: el disco completo se escanea una vez y las siguientes ejecuciones arrancan al instante (`F5` para re-escanear).

## Requisitos

- Python 3.10 o superior.

## Instalación y uso

### Windows (CMD o PowerShell)

```cmd
:: 1. Ve a la carpeta del proyecto
cd buscadorArchivos

:: 2. Instala (dependencias + comando global "buscador")
instalar.cmd

:: 3. Úsalo desde cualquier terminal
buscador
buscador "C:\Users\rcg70\Documents"
```

### Linux Ubuntu (terminal)

```bash
# 1. Ve a la carpeta del proyecto
cd buscadorArchivos

# 2. Instala (dependencias + comando global "buscador")
bash instalar.sh

# 3. Úsalo desde cualquier terminal
buscador
buscador /media/datos ~/Documentos
```

Si `buscador` no se encuentra después de instalar, agrega `~/.local/bin` a tu PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

### Alternativa manual (sin el instalador, en ambos sistemas)

```bash
python -m pip install -r requirements.txt
python -m buscador            # todo el disco
python -m buscador "C:\ruta"  # carpetas concretas
```

Otra opción estándar (requiere que tu Python tenga `Scripts` en PATH):
```bash
python -m pip install -e .
buscador
```

## Cómo funciona

- Sin argumentos busca en todo el disco (todos los rígidos en Windows, `/` en Linux); con rutas, solo en esas carpetas.
- El primer escaneo de todo el disco puede tardar unos minutos; el resultado se guarda en caché en tu perfil de usuario (un archivo por ámbito: disco completo o cada carpeta elegida con `/`):
  - Windows: `%LOCALAPPDATA%\buscador-archivo\cache_<hash>.json`
  - Ubuntu: `~/.cache/buscador-archivo/cache_<hash>.json`
- Los cambios del disco (archivos creados o borrados después del último escaneo) se reflejan con `F5`.
- **Al abrir, la caché se verifica en segundo plano:** los archivos ya borrados del disco se descartan de la lista (y se limpian de la caché) sin re-escanear; para detectar los **nuevos** sigue siendo necesario `F5`.
- **Enviar a la papelera (Ctrl+Supr):** en Windows va a la Papelera de reciclaje y se puede restaurar desde ahí; en Ubuntu usa `trash-put` si está instalado y, si no existe, lo borra definitivamente (con confirmación previa en ambos casos). El archivo desaparece de la tabla al instante y no vuelve a aparecer con resultados de caché en curso. El borrado permanente lo haces tú desde la papelera, fuera del programa.
- **Vigilancia automática:** cada pocos segundos se comprueba en segundo plano que los archivos visibles sigan existiendo; los borrados fuera del buscador (Explorador, papelera, otro equipo...) salen de la tabla solos, sin F5 y sin re-escanear.
- El tema elegido con `Ctrl+T` se guarda en `preferencias.json` junto a las cachés.

## Atajos

| Tecla | Acción |
|-------|--------|
| (escribir) | Filtrar resultados al instante |
| `*` / `?` | Comodines de patrón (`informe*`, `*.pdf`, `plan?2026`) |
| `/` | Desplegar panel de carpetas habituales (elegir dónde buscar) |
| ↑ / ↓ | Moverse entre resultados |
| Enter / doble clic | Abrir archivo seleccionado |
| Ctrl+O | Abrir la carpeta contenedora del archivo resaltado |
| Ctrl+C | Copiar la ruta completa al portapapeles |
| Ctrl+T | Cambiar el tema de colores (se recuerda entre sesiones) |
| F2 / F3 / F4 | Filtrar: solo Word / Excel / PowerPoint |
| F6 / F7 | Filtrar: solo PDF / LibreOffice (se apilan con lo escrito) |
| F8 / F9 | Cambiar la columna de orden / alternar ascendente‑descendente |
| F10 | Modo solo duplicados: solo nombres que se repiten (activa/desactiva) |
| Ctrl+Supr | Enviar a la papelera el archivo resaltado (pregunta antes) |
| F5 | Re-escanear el disco y actualizar la caché |
| Ctrl+D | Borrar caché y re-escanear de cero |
| F1 | Ayuda: atajos y funciones (pantalla flotante) |
| Esc / Ctrl+Q | Salir a la terminal |

## Exclusiones

Puedes indicar carpetas que el escaneo debe ignorar creando (o editando) el
archivo `excluir.txt` junto a la caché (`%LOCALAPPDATA%\buscador-archivo\excluir.txt`
en Windows; `~/.cache/buscador-archivo/excluir.txt` en Ubuntu). Cada línea no
comentada es un fragmento de la ruta de carpeta a ignorar (insensible a
mayúsculas) y admite comodines `*` y `?`. Se aplica en el siguiente escaneo:

```
# ejemplo
node_modules
C:\Users\*\AppData\Local\Packages
```

## Estructura del código

```
buscador/
├── escaner.py   # recorre el disco, filtra extensiones, guarda y carga la caché
├── app.py       # interfaz TUI (Textual): búsqueda en vivo + tabla de resultados
└── __main__.py  # punto de entrada (python -m buscador)
```

## Licencia

MIT
