#!/bin/bash

# Test script for version detection and strategy determination

# Source the required functions from install.sh
source <(grep -A 50 "^detect_architecture()" install.sh)
source <(grep -A 50 "^version_compare()" install.sh)
source <(grep -A 30 "^get_installed_version()" install.sh)
source <(grep -A 40 "^get_apt_version()" install.sh)
source <(grep -A 20 "^check_version_requirement()" install.sh)
source <(grep -A 50 "^determine_install_strategy()" install.sh)

# Declare arrays like in main script
declare -gA TOOL_MIN_VERSIONS
declare -gA TOOL_APT_PACKAGES
declare -gA TOOL_CHECK_COMMANDS
declare -gA TOOL_REQUIRED_BY
declare -gA TOOL_MANUAL_INSTALL
declare -gA INSTALL_STRATEGY
declare -gA APT_AVAILABLE_VERSIONS

# Set up tool registry
TOOL_MIN_VERSIONS["golang"]="1.21.0"
TOOL_APT_PACKAGES["golang"]="golang"
TOOL_CHECK_COMMANDS["golang"]="go version 2>/dev/null | awk '{print \$3}' | sed 's/go//'"
TOOL_REQUIRED_BY["golang"]="katana, subfinder"
TOOL_MANUAL_INSTALL["golang"]="golang_tarball"

TOOL_MIN_VERSIONS["java"]="11.0.0"
TOOL_APT_PACKAGES["java"]="openjdk-21-jre"
TOOL_CHECK_COMMANDS["java"]="java -version 2>&1 | grep -oP 'version \"?\K[0-9]+\.[0-9]+\.[0-9]+' | head -n1"
TOOL_REQUIRED_BY["java"]="OWASP ZAP"
TOOL_MANUAL_INSTALL["java"]="openjdk_tarball"

TOOL_MIN_VERSIONS["nodejs"]="20.0.0"
TOOL_APT_PACKAGES["nodejs"]="nodejs"
TOOL_CHECK_COMMANDS["nodejs"]="node --version 2>/dev/null | sed 's/v//'"
TOOL_REQUIRED_BY["nodejs"]="MDN Observatory CLI"
TOOL_MANUAL_INSTALL["nodejs"]="nodesource_repo"

echo "========================================"
echo "Testing Version Detection Functions"
echo "========================================"
echo ""

# Test architecture detection
echo "1. Testing architecture detection..."
arch=$(detect_architecture)
echo "   Detected architecture: $arch"
echo ""

# Test version comparison
echo "2. Testing version comparison..."
if version_compare "1.21.5" "1.21.0"; then
    echo "   ✓ 1.21.5 >= 1.21.0 (PASS)"
else
    echo "   ✗ 1.21.5 >= 1.21.0 (FAIL)"
fi

if version_compare "1.19.0" "1.21.0"; then
    echo "   ✗ 1.19.0 >= 1.21.0 should be FALSE (FAIL)"
else
    echo "   ✓ 1.19.0 >= 1.21.0 is FALSE (PASS)"
fi
echo ""

# Test APT version detection
echo "3. Testing APT version detection..."
for tool in golang java nodejs; do
    package="${TOOL_APT_PACKAGES[$tool]}"
    echo "   Testing: $package"
    
    apt_ver=$(get_apt_version "$package")
    if [[ $? -eq 0 ]] && [[ -n "$apt_ver" ]]; then
        echo "     APT version: $apt_ver"
    else
        echo "     APT version: Not available"
    fi
done
echo ""

# Test installed version detection
echo "4. Testing installed version detection..."
for tool in golang java nodejs; do
    echo "   Testing: $tool"
    
    inst_ver=$(get_installed_version "$tool")
    if [[ -n "$inst_ver" ]]; then
        echo "     Installed version: $inst_ver"
    else
        echo "     Installed version: Not installed"
    fi
done
echo ""

# Test strategy determination
echo "5. Testing installation strategy determination..."
for tool in golang java nodejs; do
    echo "   Testing: $tool"
    
    strategy=$(determine_install_strategy "$tool")
    echo "     Strategy: $strategy"
    
    INSTALL_STRATEGY["$tool"]="$strategy"
done
echo ""

# Verify strategies were stored
echo "6. Verifying strategies were stored in array..."
for tool in golang java nodejs; do
    echo "   INSTALL_STRATEGY[$tool] = '${INSTALL_STRATEGY[$tool]}'"
done
echo ""

echo "========================================"
echo "Test Complete"
echo "========================================"
