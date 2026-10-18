# buscadorArchivos

Buscador de archivos de Office (Word, Excel, PowerPoint, LibreOffice) y PDF **solo por nombre**, con resultado mientras escribes, fichas con nombre/tipo/fechas/peso y lista navegable con teclado (↑↓, Enter para abrir) y ratón (doble clic). Interfaz TUI en Python + [Textual](https://textual.textualize.io). Windows y Ubuntu.

## Instalación (terminal)

**Windows (CMD o PowerShell):**
```cmd
instalar.cmd
```
Deja el comando `buscador` disponible en cualquier terminal (crea un lanzador en `%LOCALAPPDATA%\Microsoft\WindowsApps`, sin permisos de administrador).

**Ubuntu:**
```bash
bash instalar.sh
```
Crea `~/.local/bin/buscador` (asegúrate de tener `~/.local/bin` en tu PATH).

Alternativa universal (si la carpeta `Scripts` de tu Python está en PATH):
```bash
python -m pip install -e .
```

## Uso

```
buscador                  # busca en todo el disco (todos los rígidos en Windows, / en Linux)
buscador "C:\Users\yo\Docs"   # busca solo en carpetas concretas
```

- Escribe en el campo de arriba: los resultados se filtran al vuelo.
- ↑↓ para moverte, **Enter o doble clic** abre el archivo con la app predeterminada.
- **F5** re-escanea el disco en segundo plano y actualiza la caché.
- **Ctrl+Q** para salir.

## Caché

El primer escaneo de todo el disco puede tardar minutos; el resultado se guarda en
`%LOCALAPPDATA%\buscador-archivo\cache.json` (Windows) o `~/.cache/buscador-archivo/cache.json` (Ubuntu).
Las siguientes veces la app carga la caché al instante. Los cambios del disco (archivos nuevos o borrados)
se reflejan con F5.
