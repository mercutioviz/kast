#!/bin/bash

# KAST - Kali Automated Scanning Tool
# Installation Script

## For fun print out the ANSI Kast logo
if [ -f "./assets/mascot.ans" ]; then
  cat ./assets/mascot.ans
fi

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
  read -p "Would you like to create it? (Y/n): " create_dir
  
  if [[ $create_dir =~ ^[Yy]$ || -z $create_dir ]]; then
    echo -e "${YELLOW}[*] Creating installation directory: $INSTALL_DIR${NC}"
    mkdir -p "$INSTALL_DIR"
  else
    echo -e "${RED}[!] Installation aborted. Directory does not exist.${NC}"
    exit 1
  fi
fi

# Update package lists
echo -e "${YELLOW}[*] Updating package lists${NC}"
apt-get update

# Install system dependencies
echo -e "${YELLOW}[*] Installing system dependencies${NC}"
apt-get install -y python3 python3-pip python3-venv git curl wget jq whois dnsutils npm man-db screen

# Copy files to installation directory
echo -e "${YELLOW}[*] Copying files to $INSTALL_DIR${NC}"
cp -r ./* "$INSTALL_DIR/"

# Create results directory
mkdir -p "$INSTALL_DIR/results"
echo -e "${YELLOW}[*] Setting permissions for results directory${NC}"
chmod 777 "$INSTALL_DIR/results"
echo -e "Do chown -R \"$SUDO_USER:$SUDO_USER\" $INSTALL_DIR"
chown -R "$SUDO_USER:$SUDO_USER" "$INSTALL_DIR"

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
        "python-owasp-zap-v2.4>=0.0.20",
        "pyjwt>=2.4.0",
        "pandas>=1.4.0",
        "matplotlib>=3.5.0",
        "droopescan>=1.45.1",
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

# Install the package in development mode
echo -e "${YELLOW}[*] Installing KAST package${NC}"
cd "$INSTALL_DIR"
if pip install -e .; then
  echo -e "${GREEN}[+] KAST package installed successfully${NC}"
else
  echo -e "${RED}[!] Error installing KAST package. You may need to install it manually.${NC}"
fi

# Check for and install system dependencies
echo -e "${YELLOW}[*] Checking for required system tools${NC}"
required_tools=("whatweb" "theharvester" "maltego" "dnsenum" "sslscan" "zaproxy" "nikto" "wapiti" "metasploit-framework" "burpsuite" "sqlmap" "wafw00f" "wpscan" "joomscan" "nuclei" "dirb" "dirbuster" "nmap" "masscan" "testssl.sh" "sublist3r")

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

# Install zaproxy addons
echo -e "${YELLOW}[*]Installing zaproxy addons${NC}"
zaproxy -addoninstallall -cmd

# Special case for testssl.sh which might be named differently
if ! command -v testssl.sh &> /dev/null && ! command -v testssl &> /dev/null; then
  echo -e "${YELLOW}[*] Installing testssl.sh${NC}"
  apt-get install -y testssl.sh || {
    echo -e "${YELLOW}[*] Trying alternative installation method for testssl.sh${NC}"
    git clone --depth 1 https://github.com/drwetter/testssl.sh.git /opt/testssl.sh
    ln -sf /opt/testssl.sh/testssl.sh /usr/local/bin/testssl.sh
  }
fi

# Install pandoc
echo -e "${YELLOW}[*] Installing pandoc${NC}"
if ! command -v pandoc &> /dev/null; then
  apt-get install -y pandoc
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}[+] pandoc installed successfully${NC}"
  else
    echo -e "${RED}[!] Failed to install pandoc. You may need to install it manually.${NC}"
  fi
else
  echo -e "${GREEN}[+] pandoc is already installed${NC}"
fi

# Check for and install mdn-http-observatory
echo -e "${YELLOW}[*] Checking for mdn-http-observatory${NC}"
if ! command -v observatory &> /dev/null; then
  echo -e "${YELLOW}[*] Installing mdn-http-observatory${NC}"
  npm install -g observatory-cli
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}[+] mdn-http-observatory installed successfully${NC}"
  else
    echo -e "${RED}[!] Failed to install mdn-http-observatory. You may need to install it manually:${NC}"
    echo -e "${YELLOW}    npm install -g observatory-cli${NC}"
  fi
else
  echo -e "${GREEN}[+] mdn-http-observatory is already installed${NC}"
fi

# Create wrapper script for easy execution
echo -e "${YELLOW}[*] Creating wrapper script for KAST${NC}"
cat > /usr/local/bin/kast << EOF
#!/bin/bash
cd "$INSTALL_DIR"
source "$INSTALL_DIR/venv-kast/bin/activate"
python "$INSTALL_DIR/src/main.py" "\$@"
EOF
chmod +x /usr/local/bin/kast

echo -e "${GREEN}[+] KAST has been successfully installed!${NC}"
echo -e "${GREEN}[+] You can now run the tool by typing 'kast' in your terminal${NC}"
echo -e "${YELLOW}[*] Remember to use this tool responsibly and legally${NC}"

# Create default configuration
echo -e "${YELLOW}[*] Creating default configuration${NC}"
mkdir -p ~/.config/kast
cat > ~/.config/kast/config.yaml << 'EOF'
# KAST Configuration

# API Keys
api_keys:
  securityheaders: ""  # Get your API key from https://securityheaders.com/api
  ssllabs: ""
  # Add other API keys as needed

# Scan Settings
scan_settings:
  # Reconnaissance settings
  recon:
    use_browser: true
    use_online_services: true
    
  # Vulnerability scanning settings
  vuln:
    nikto:
      default_type: "basic"  # basic, quick, thorough
      timeout:
        basic: 1800    # 30 minutes
        quick: 600     # 10 minutes
        thorough: 3600  # 60 minutes

# Output Settings
output:
  default_directory: ""  # Leave empty to use the default location
  report_format: "html"  # html, json, or both
EOF

echo -e "${GREEN}[+] Default configuration created at ~/.config/kast/config.yaml${NC}"
echo -e "${YELLOW}[*] You may want to edit this file to add your API keys and customize settings${NC}"
