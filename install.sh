#!/bin/bash

echo "Welcome to the KAST Installation Script."
echo "You must type YES to agree to use KAST within legal limits and responsibly."
read -p "Type YES to agree: " user_agree

if [[ $user_agree != "YES" ]]; then
    echo "You did not agree to the terms. Exiting installation."
    exit 1
fi

echo "Select the installation directory for KAST (default is /opt/kast):"
read -p "Press enter for default or specify a different path: " install_path

if [[ -z "$install_path" ]]; then
    install_path="/opt/kast"
fi

# Create the directory if it doesn't exist
mkdir -p "$install_path"
cd "$install_path"

# Clone the repository into the chosen directory
# git clone https://github.com/yourusername/kast.git "$install_path" 
# Assuming the user does this part manually as per the user's plan

# Setup Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

echo "Installation completed successfully."
echo "You can run KAST from $install_path/src/main.py"
