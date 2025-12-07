#!/bin/bash

set -e

ORIG_USER=${SUDO_USER:-$USER}
ORIG_HOME=$(getent passwd "$ORIG_USER" | cut -d: -f6)

cat assets/mascot.ans

# Require root
if [[ $EUID -ne 0 ]]; then
   echo "This installer must be run as root (use sudo)" 1>&2
   exit 1
fi

echo "Welcome to the KAST Installer"
echo "KAST works best on a fresh Debian or Kali instance."
echo "The installer will attempt to install or update several tools."
echo "Proceed with caution."
echo
read -p "Enter install directory [/opt/kast]: " INSTALL_DIR
INSTALL_DIR=${INSTALL_DIR:-/opt/kast}

# Install Node.js (includes npm)
apt install -y ca-certificates curl gnupg rsync
apt install -y firefox-esr git golang gpg htop nginx openjdk-21-jre python3 python3-venv sslscan testssl.sh wafw00f whatweb
mkdir -p /etc/apt/keyrings
curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --yes --dearmor -o /etc/apt/keyrings/nodesource.gpg
echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list
apt update
apt install -y nodejs

# Install projectdiscover items
mkdir -p "$ORIG_HOME/go/bin"
GOBIN="$ORIG_HOME/go/bin" CGO_ENABLED=1 go install github.com/projectdiscovery/katana/cmd/katana@latest
ln -f -s $ORIG_HOME/go/bin/katana /usr/local/bin/katana
GOBIN="$ORIG_HOME/go/bin" go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
ln -f -s $ORIG_HOME/go/bin/subfinder /usr/local/bin/subfinder

## install the necessary gecko driver for firefox automation
GECKO_VERSION=$(curl -s https://api.github.com/repos/mozilla/geckodriver/releases/latest | grep 'tag_name' | cut -d '"' -f 4)
echo $GECKO_VERSION
wget -q "https://github.com/mozilla/geckodriver/releases/download/$GECKO_VERSION/geckodriver-$GECKO_VERSION-linux64.tar.gz"
tar -xzf geckodriver-*-linux64.tar.gz
mv geckodriver /usr/local/bin/
rm geckodriver-*-linux64.tar.gz
geckodriver --version

## Install terraform
wget -O - https://apt.releases.hashicorp.com/gpg | gpg --yes --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(grep -oP '(?<=UBUNTU_CODENAME=).*' /etc/os-release || lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list
apt update && apt install terraform

# Install MDN Observatory CLI tool
npm install --global @mdn/mdn-http-observatory --unsafe-perm

# Install libpango for PDF generation
apt install -y libpango-1.0-0 libpangoft2-1.0-0

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

# Create launcher script
echo "Creating launcher script at /usr/local/bin/kast..."
cat > /usr/local/bin/kast <<EOF
#!/bin/bash
KAST_DIR="$INSTALL_DIR"
source "\$KAST_DIR/venv/bin/activate"
cd "\$KAST_DIR"
python -m kast.main "\$@"
EOF

# Install custom ftap
cd $ORIG_HOME
git clone https://github.com/mercutioviz/ftap
cd ftap
echo "Creating launcher script at /usr/local/bin/ftap..."
cat > /usr/local/bin/ftap <<EOF
#!/bin/bash
FTAP_DIR="$ORIG_HOME/ftap"
source "\$KAST_DIR/venv/bin/activate"
cd "\$FTAP_DIR"
python -m finder.py "\$@"
EOF

chmod +x /usr/local/bin/kast
chmod +x /usr/local/bin/ftap

# Create default target log directory
mkdir -p /var/log/kast
chown $ORIG_USER:$ORIG_USER /var/log/kast

echo "KAST installed! Run 'kast --help' to get started."
