#!/bin/bash

set -e

# Require root
if [[ $EUID -ne 0 ]]; then
   echo "This installer must be run as root (use sudo)" 1>&2
   exit 1
fi

echo "KAST Installer"
read -p "Enter install directory [/opt/kast]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-/opt/kast}

echo "Installing to $INSTALL_DIR"

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Copy project files, excluding the install script itself
echo "Copying project files..."
echo "Skipping $(basename "$0")"
echo "Skipping .git"

rsync -av --exclude="$(basename "$0")" --exclude=".git" ./ "$INSTALL_DIR/"

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3 -m venv "$INSTALL_DIR/venv"

# Create requirements.txt if it doesn't exist
if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
    echo "# KAST requirements" > "$INSTALL_DIR/requirements.txt"
fi

# Install requirements
echo "Installing Python dependencies..."
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Install npm
apt install npm -y

# Install MDN Observatory CLI tool
npm install --global @mdn/mdn-http-observatory

# Create launcher script
echo "Creating launcher script at /usr/local/bin/kast..."
cat > /usr/local/bin/kast <<EOF
#!/bin/bash
KAST_DIR="$INSTALL_DIR"
source "\$KAST_DIR/venv/bin/activate"
cd "\$KAST_DIR"
python -m kast.main "\$@"
EOF

chmod +x /usr/local/bin/kast

echo "KAST installed! Run 'kast --help' to get started."
