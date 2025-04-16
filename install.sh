#!/bin/bash

# KAST - Kali Automated Scanning Tool
# Installation Script

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[!] This script must be run as root${NC}"
  exit 1
fi

# Check if running on Kali Linux
if ! grep -q 'Kali' /etc/os-release; then
  echo -e "${YELLOW}[!] Warning: This script is designed for Kali Linux.${NC}"
  echo -e "${YELLOW}[!] Running on a different distribution may cause issues with package names.${NC}"
  read -p "Do you want to continue anyway? (y/N): " continue_anyway
  if [[ ! $continue_anyway =~ ^[Yy]$ ]]; then
    echo -e "${RED}[!] Installation aborted.${NC}"
    exit 1
  fi
fi

# Ethical usage agreement
echo -e "${YELLOW}[*] IMPORTANT: This tool should only be used for authorized security testing.${NC}"
echo -e "${YELLOW}[*] Unauthorized scanning of systems is illegal and unethical.${NC}"
echo -e "${YELLOW}[*] By proceeding, you agree to use this tool responsibly and legally.${NC}"
read -p "Type 'YES' to confirm you will use this tool ethically: " ethical_agreement

if [ "$ethical_agreement" != "YES" ]; then
  echo -e "${RED}[!] Installation aborted. You must agree to use this tool ethically.${NC}"
  exit 1
fi

# Default installation directory
DEFAULT_DIR="/opt/kast"
INSTALL_DIR=$DEFAULT_DIR

# Ask for installation directory
echo -e "${YELLOW}[*] KAST will be installed in ${DEFAULT_DIR} by default.${NC}"
read -p "Enter installation directory (or press Enter for default): " user_dir

if [ -n "$user_dir" ]; then
  INSTALL_DIR=$user_dir
fi

# Check if directory exists, if not ask to create it
if [ ! -d "$INSTALL_DIR" ]; then
  echo -e "${YELLOW}[*] Directory $INSTALL_DIR does not exist.${NC}"
  read -p "Would you like to create it? (y/N): " create_dir
  
  if [[ $create_dir =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}[*] Creating installation directory: $INSTALL_DIR${NC}"
    mkdir -p "$INSTALL_DIR"
  else
    echo -e "${RED}[!] Installation aborted. Directory does not exist.${NC}"
    exit 1
  fi
fi

# Copy files to installation directory
echo -e "${YELLOW}[*] Copying files to $INSTALL_DIR${NC}"
cp -r ./* "$INSTALL_DIR/"

# Create reports directory
mkdir -p "$INSTALL_DIR/reports"

# Create results directory
mkdir -p "$INSTALL_DIR/results"
chmod 666 "$INSTALL_DIR/results"

# Create a setup.py file for proper package installation
echo -e "${YELLOW}[*] Creating setup.py for package installation${NC}"
cat > "$INSTALL_DIR/setup.py" << 'EOF'
from setuptools import setup, find_packages

setup(
    name="kast",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "pyppeteer>=1.0.2",
        "requests>=2.27.1",
        "beautifulsoup4>=4.10.0",
        "python-nmap>=0.7.1",
        "colorama>=0.4.4",
        "pyyaml>=6.0",
        "jinja2>=3.0.3",
        "rich>=12.0.0",
    ],
)
EOF

# Set up Python virtual environment
echo -e "${YELLOW}[*] Setting up Python virtual environment${NC}"
python3 -m venv "$INSTALL_DIR/venv-kast"
source "$INSTALL_DIR/venv-kast/bin/activate"

# Install Python dependencies with error handling
echo -e "${YELLOW}[*] Installing Python dependencies${NC}"
if pip install -r "$INSTALL_DIR/requirements.txt"; then
  echo -e "${GREEN}[+] Python dependencies installed successfully${NC}"
else
  echo -e "${RED}[!] Error installing Python dependencies. Please check your internet connection and try again.${NC}"
  echo -e "${YELLOW}[*] You can manually install dependencies later with: source $INSTALL_DIR/venv-kast/bin/activate && pip install -r $INSTALL_DIR/requirements.txt${NC}"
fi

# Check for and install system dependencies
echo -e "${YELLOW}[*] Checking for required system tools${NC}"
required_tools=("whatweb" "theharvester" "maltego" "dnsenum" "sslscan" "zaproxy" "nikto" "wapiti" "metasploit-framework" "burpsuite" "sqlmap" "wafw00f")

for tool in "${required_tools[@]}"; do
  if ! command -v $tool &> /dev/null; then
    echo -e "${YELLOW}[*] Installing $tool${NC}"
    if apt-get install -y $tool; then
      echo -e "${GREEN}[+] $tool installed successfully${NC}"
    else
      echo -e "${RED}[!] Failed to install $tool. You may need to install it manually.${NC}"
    fi
  else
    echo -e "${GREEN}[+] $tool is already installed${NC}"
  fi
done

# Create symlink for easy execution
# Create wrapper script for easy execution
echo -e "${YELLOW}[*] Creating wrapper script for KAST${NC}"
cat > /usr/local/bin/kast << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source "$INSTALL_DIR/venv-kast/bin/activate"
python "$INSTALL_DIR/src/main.py" "\$@"
EOF

chmod +x /usr/local/bin/kast
chmod +x "$INSTALL_DIR/src/main.py"

echo -e "${GREEN}[+] KAST has been successfully installed!${NC}"
echo -e "${GREEN}[+] You can now run the tool by typing 'kast' in your terminal${NC}"
echo -e "${YELLOW}[*] Remember to use this tool responsibly and legally${NC}"
