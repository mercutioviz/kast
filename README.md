![image](https://github.com/user-attachments/assets/d6758a51-cb37-431d-b044-3baf1f8ff80b)

# KAST - Kali Automated Scanning Tool

KAST (Kali Automated Scanning Tool) is a comprehensive web application security scanning tool designed for Kali Linux. It automates the process of detecting vulnerabilities using various security tools and provides options for both reconnaissance and vulnerability scanning.

## Features

- **Comprehensive Reconnaissance**: Utilizes multiple tools to gather information about the target:
  - WhatWeb for technology detection
  - theHarvester for email and subdomain enumeration
  - DNSenum for DNS information gathering
  - SSLScan for SSL/TLS configuration analysis
  - wafw00f for Web Application Firewall detection
  - Browser-based reconnaissance using pyppeteer

- **Online Security Services Integration**:
  - SSL Labs API for comprehensive SSL/TLS analysis
  - SecurityHeaders.io for HTTP security headers analysis
  - Mozilla Observatory for web security analysis

- **Detailed Reporting**: Generates structured reports with findings from all tools

- **Logging System**: Maintains detailed logs of all operations for audit and review

## Installation

### Prerequisites

- Kali Linux (recommended) or other Debian-based distributions
- Python 3.7+
- Root privileges for installing system dependencies

### Installation Steps

1. Clone the repository:
```bash
git clone https://github.com/yourusername/kast.git && cd kast
```
2. Run the installation script:
```bash
sudo ./install.sh
```
The installation script will:
   - Verify you're running as root
   - Check if you're running Kali Linux
   - Ask for ethical usage confirmation
   - Install required system dependencies
   - Set up a Python virtual environment
   - Install Python dependencies
   - Create a symlink for easy execution

3. Verify the installation:
```bash
kast --help
```
## Usage

### Basic Usage
```bash
kast [target]
```
Where `[target]` can be a URL, domain, or IP address.

### Advanced Options
```bash
kast [target] [options]
```
Options:
- `-m, --mode`: Scan mode (recon, vuln, full)
- `-o, --output`: Custom output directory
- `-q, --quiet`: Quiet mode, minimal output
- `--no-browser`: Disable browser-based scanning
- `--no-online`: Disable online services (SSL Labs, SecurityHeaders.io, Mozilla Observatory)

### Examples

# Full scan of a website
```bash
kast https://example.com
```
# Reconnaissance only
```bash
kast example.com -m recon
```

# Vulnerability scan with custom output directory
```bash
kast 192.168.1.1 -m vuln -o /path/to/results
```

# Full scan without browser-based tests
```bash
kast example.com --no-browser
```

## Results

Scan results are stored in the results directory with the following structure:

```
results/
└── domain-YYYY-MM-DD-HH-MM-SS/
    ├── logs/
    │   └── kast-YYYYMMDD-HHMMSS.log
    ├── recon/
    │   ├── whatweb.json
    │   ├── theharvester.xml
    │   ├── theharvester_parsed.json
    │   ├── dnsenum.xml
    │   ├── dnsenum_parsed.json
    │   ├── sslscan.json
    │   ├── wafw00f.json
    │   ├── browser_recon.json
    │   ├── screenshot.png
    │   ├── ssllabs.json
    │   ├── securityheaders.json
    │   └── mozilla_observatory.json
    └── vuln/
        └── [vulnerability scan results]
```

## Tools Used

KAST integrates with the following tools:

- WhatWeb
- theHarvester
- DNSenum
- SSLScan
- wafw00f
- Nikto
- Wapiti
- SQLmap
- Metasploit Framework
- Burp Suite (with paid professional edition)
- ZAP (OWASP Zed Attack Proxy)

## Ethical Usage Disclaimer
IMPORTANT: KAST is designed for authorized security testing only. Unauthorized scanning of systems is illegal and unethical. Always ensure you have explicit permission to scan any target system.

By using this tool, you agree to:

Only scan systems you own or have explicit permission to test
Comply with all applicable laws and regulations
Use the tool responsibly and ethically
Accept full responsibility for your actions
The developers of KAST are not responsible for any misuse or damage caused by this tool.

License
This project is licensed under the MIT License - see the LICENSE file for details.
