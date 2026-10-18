#!/usr/bin/env bash
# Instalador para Ubuntu: ejecutar con  bash instalar.sh  desde la carpeta del proyecto.
# Deja el comando "buscador" disponible en la terminal.
set -e
cd "$(dirname "$0")"

echo "[1/2] Instalando dependencias..."
python3 -m pip install --user -r requirements.txt

echo "[2/2] Creando el comando 'buscador'..."
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/buscador" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="\$PYTHONPATH:$(pwd)"
exec python3 -m buscador "\$@"
EOF
chmod +x "$HOME/.local/bin/buscador"

echo ""
echo "Listo. Ejecuta:  buscador"
echo "(con carpeta concreta:  buscador /media/datos)"
echo "Si el comando no se encuentra, agrega ~/.local/bin a tu PATH."
