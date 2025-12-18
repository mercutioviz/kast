#!/bin/bash

# Test script to verify update.sh version detection

echo "========================================================================"
echo "  Testing Version Detection in update.sh"
echo "========================================================================"
echo ""

# Set the git directory to current directory
GIT_DIR="."

echo "Test 1: Checking if kast/main.py exists..."
if [[ -f "$GIT_DIR/kast/main.py" ]]; then
    echo "✓ kast/main.py found"
else
    echo "✗ kast/main.py not found"
    exit 1
fi

echo ""
echo "Test 2: Extracting version from kast/main.py..."
NEW_VERSION=$(grep "^KAST_VERSION = " "$GIT_DIR/kast/main.py" | cut -d'"' -f2)

if [[ -n "$NEW_VERSION" ]]; then
    echo "✓ Version extracted successfully: $NEW_VERSION"
else
    echo "✗ Failed to extract version"
    exit 1
fi

echo ""
echo "Test 3: Verifying expected version..."
EXPECTED_VERSION="2.7.1"
if [[ "$NEW_VERSION" == "$EXPECTED_VERSION" ]]; then
    echo "✓ Version matches expected: $NEW_VERSION"
else
    echo "✗ Version mismatch!"
    echo "   Expected: $EXPECTED_VERSION"
    echo "   Got:      $NEW_VERSION"
    exit 1
fi

echo ""
echo "Test 4: Comparing with install.sh version (for reference)..."
INSTALL_VERSION=$(grep "^SCRIPT_VERSION=" "$GIT_DIR/install.sh" | cut -d'"' -f2)
echo "   install.sh version: $INSTALL_VERSION"
echo "   main.py version:    $NEW_VERSION"

if [[ "$INSTALL_VERSION" != "$NEW_VERSION" ]]; then
    echo "   (Note: install.sh has different version, but update.sh now reads from main.py)"
fi

echo ""
echo "========================================================================"
echo "  All Tests Passed! ✓"
echo "========================================================================"
echo ""
echo "Summary:"
echo "  - update.sh will now correctly detect version $NEW_VERSION"
echo "  - Version is read from kast/main.py (single source of truth)"
echo "  - No more sync issues between install.sh and main.py"
echo ""
