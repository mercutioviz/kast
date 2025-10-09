#!/bin/bash

# File to write the prompt into
PROMPT_FILE="AI-Prompts.txt"

# Run tree command and capture output
TREE_OUTPUT=$(tree /opt/kast/kast -I "*.pyc" -I "__pycache__")

# Write the enhanced prompt to the file
cat <<EOF > "$PROMPT_FILE"
# Role: I am a Solutions Architect specializing in Web Application Firewalls (WAFs).
# Project: I'm building a Python-based tool called KAST (Kali Automated Scan Tool).
# Purpose: KAST automates vulnerability scanning using tools available in Kali Linux.
# Structure: KAST is modular. Here's the current directory layout:
$TREE_OUTPUT

# Plugin Design:
# - Each plugin represents a scanning tool and inherits from base.py
# - Plugins are categorized as either 'active' or 'passive'
#   - Active scans require explicit permission to run against a target
#   - Passive scans are safe to run without permission
# - Each plugin returns structured JSON with:
#   - 'details': raw or parsed output
#   - 'summary': high-level findings
#   - 'report': key points to include in the final report
#   - 'issues': list of identified problems with brief remediation suggestions

# Reporting Goals:
# - The final report should include:
#   - Executive Summary
#   - Issues Found (with brief WAF-related remediation suggestions)
#   - Detailed Results per Tool
# - Example issue blurb:
#   - If TLSv1.0 is detected: "TLSv1.0 is considered insecure by some in the industry. A WAF can easily add TLSv1.2 or 1.3 by front-ending your web application."

# Task: Today I want to add a new plugin for the 'nikto' web server scanner.
# Requirements:
# - The plugin should inherit from base.py
# - It should execute 'nikto' via subprocess and parse the output
# - Categorize it as an 'active' scan
# - Return structured JSON with 'details', 'summary', 'report', and 'issues'
# - Include error handling and logging
# - Use only standard Python libraries
# - Add comments explaining each step
EOF

echo "Prompt written to $PROMPT_FILE"
