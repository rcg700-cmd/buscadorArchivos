# buscadorArchivos

Buscador de archivos de Office (Word, Excel, PowerPoint, LibreOffice) y PDF **solo por nombre**, con resultado mientras escribes, fichas con nombre/tipo/fechas/peso y lista navegable con teclado (↑↓, Enter para abrir) y ratón (doble clic). Interfaz TUI en Python + [Textual](https://textual.textualize.io). Windows y Ubuntu.

## Instalación y uso

### Windows (CMD o PowerShell)

```cmd
:: 1. Ir a la carpeta del proyecto
cd "C:\Users\rcg70\OneDrive\Documentos\open code\buscadorArchivos"

:: 2. Instalar (dependencias + comando global "buscador")
instalar.cmd

:: 3. Usar desde cualquier terminal
buscador
buscador "C:\Users\rcg70\Documents"
```

### Linux Ubuntu (terminal)

```bash
# 1. Ir a la carpeta del proyecto (ajusta la ruta si la copiaste a otra parte)
cd ~/Documentos/buscadorArchivos

# 2. Instalar (dependencias + comando global "buscador")
bash instalar.sh

# 3. Usar desde cualquier terminal
buscador
buscador /media/datos
buscador ~/Documentos
```

Si `buscador` no se encuentra después de instalar, agrega `~/.local/bin` a tu PATH:
```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

### Alternativa manual (sin el instalador)

```bash
# Igual en Windows (con python) y Ubuntu (con python3):
python -m pip install -r requirements.txt
python -m buscador            # todo el disco
python -m buscador "C:\ruta"  # carpetas concretas
```

Otra opción estándar con pip (requiere que tu Python tenga `Scripts` en PATH):
```bash
python -m pip install -e .
buscador
```

### Atajos

- Escribe y filtra al instante ↑↓ para navegar.
- **Enter / doble clic** abre el archivo.
- **F5** re-escanea el disco y actualiza la caché.
- **Ctrl+Q** salir.

## Caché

El primer escaneo de todo el disco puede tardar minutos; el resultado se guarda en
`%LOCALAPPDATA%\buscador-archivo\cache.json` (Windows) o `~/.cache/buscador-archivo/cache.json` (Ubuntu).
Las siguientes veces la app carga la caché al instante. Los cambios del disco (archivos nuevos o borrados)
se reflejan con F5.
