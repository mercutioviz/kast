# KAST - Kali Automated Scanning Tool

## Overview
KAST (Kali Automated Scanning Tool) is a comprehensive web application security scanning tool designed to automate the process of detecting vulnerabilities in web applications. It is built on Kali Linux and utilizes a variety of open-source tools to perform both gentle reconnaissance and thorough vulnerability scans.

KAST is intended for security professionals and developers to assess the security of their web applications in a structured and automated manner. It supports customizable scanning options and generates detailed reports that include identified vulnerabilities, CVEs, and recommendations for enhancing security, particularly through the use of Web Application Firewalls (WAFs).

## Features
- **Reconnaissance Scanning**: Gathers information without actively testing for vulnerabilities.
- **Vulnerability Scanning**: Actively tests for vulnerabilities and requires permission to perform.
- **Interactive Installation**: Customizable installation through an interactive script.
- **Comprehensive Reporting**: Detailed reports on vulnerabilities, including CVEs and security enhancement recommendations.

## Prerequisites
- Kali Linux
- Python 3
- Git (for cloning the repository)

## Installation

1. **Clone the Repository**:
bash git clone https://github.com/yourusername/kast.git && cd kast

2. **Run the Installation Script**:
bash ./install.sh

Follow the interactive prompts in the installation script to agree to legal terms and select the installation directory. The default installation directory is `/opt/kast`, but you can specify another location if desired.

3. **Activate the Virtual Environment**:
bash source venv-kast/bin/activate

4. **Run KAST**:
   Navigate to the `src` directory and run the main script:
bash python main.py

## Usage
Detailed usage instructions will be provided here, including how to select scan types, interpret results, and configure scans.

## Legal Disclaimer
KAST is intended for lawful, ethical testing and security assessment purposes only. Users must comply with all applicable local, state, and federal laws regarding access to information and technology. Misuse of KAST may result in criminal charges.

Please type `YES` when prompted by the installation script to indicate your agreement to use KAST responsibly and within legal limits.

## Contributing
Contributions to KAST are welcome. Please read the contributing guidelines before submitting pull requests.

## License
KAST is open-source software licensed under the [MIT license](LICENSE.txt).


