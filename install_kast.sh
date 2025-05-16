#!/bin/bash

echo "KAST Installer"
read -p "Enter install directory [/opt/kast]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-/opt/kast}

echo "Installing to $INSTALL_DIR"

# Create install directory if it doesn't exist
sudo mkdir -p "$INSTALL_DIR"
sudo chown "$USER":"$USER" "$INSTALL_DIR"

# Copy project files (assumes script is run from project root)
cp -r . "$INSTALL_DIR"

# Create venv
python3 -m venv "$INSTALL_DIR/venv"

# Create requirements.txt if it doesn't exist
if [ ! -f "$INSTALL_DIR/requirements.txt" ]; then
    echo "# KAST requirements" > "$INSTALL_DIR/requirements.txt"
fi

# Install requirements
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"

# Create launcher script
sudo tee /usr/local/bin/kast > /dev/null <<EOF
#!/bin/bash
source "$INSTALL_DIR/venv/bin/activate"
python -m kast.main "\$@"
EOF

sudo chmod +x /usr/local/bin/kast

echo "KAST installed! Run 'kast --help' to get started."
