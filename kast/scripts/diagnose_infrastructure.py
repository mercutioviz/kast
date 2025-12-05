#!/usr/bin/env python3
"""
Diagnostic script for troubleshooting infrastructure issues
Checks Docker, ZAP, networking, and system health

Usage:
    python diagnose_infrastructure.py /path/to/infrastructure_state.txt
"""

import sys
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ssh_executor import SSHExecutor


def print_header(message):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70 + "\n")


def print_section(message):
    """Print section header"""
    print(f"\n{'='*70}")
    print(f"  {message}")
    print(f"{'='*70}")


def print_check(message):
    """Print check message"""
    print(f"\n[CHECK] {message}")
    print("-" * 70)


def print_result(message):
    """Print result message"""
    print(f"  → {message}")


def print_success(message):
    """Print success message"""
    print(f"\n✓ {message}")


def print_error(message):
    """Print error message"""
    print(f"\n✗ {message}")


def print_warning(message):
    """Print warning message"""
    print(f"\n⚠ {message}")


def load_infrastructure_state(state_file):
    """Load infrastructure state from file"""
    state_path = Path(state_file)
    
    if not state_path.exists():
        print_error(f"State file not found: {state_file}")
        sys.exit(1)
    
    state = {}
    with open(state_path, 'r') as f:
        for line in f:
            if ':' in line:
                key, value = line.strip().split(':', 1)
                state[key.strip()] = value.strip()
    
    return state


def run_diagnostic(ssh_executor):
    """
    Run comprehensive diagnostic checks
    
    :param ssh_executor: SSH executor instance
    """
    print_header("Infrastructure Diagnostic Report")
    
    # 1. System Information
    print_section("System Information")
    
    print_check("Operating System")
    exit_code, stdout, stderr = ssh_executor.execute_command("cat /etc/os-release | grep PRETTY_NAME")
    if exit_code == 0:
        print_result(stdout.strip())
    else:
        print_error(f"Failed to get OS info: {stderr}")
    
    print_check("Kernel Version")
    exit_code, stdout, stderr = ssh_executor.execute_command("uname -r")
    if exit_code == 0:
        print_result(stdout.strip())
    
    print_check("Uptime")
    exit_code, stdout, stderr = ssh_executor.execute_command("uptime")
    if exit_code == 0:
        print_result(stdout.strip())
    
    # 2. Disk Space
    print_section("Disk Space")
    
    print_check("Filesystem Usage")
    exit_code, stdout, stderr = ssh_executor.execute_command("df -h")
    if exit_code == 0:
        print(stdout)
    else:
        print_error(f"Failed to get disk space: {stderr}")
    
    # 3. Memory
    print_section("Memory")
    
    print_check("Memory Usage")
    exit_code, stdout, stderr = ssh_executor.execute_command("free -h")
    if exit_code == 0:
        print(stdout)
    
    # 4. Docker Status
    print_section("Docker Status")
    
    print_check("Docker Installation")
    exit_code, stdout, stderr = ssh_executor.execute_command("which docker")
    if exit_code == 0:
        print_success(f"Docker installed at: {stdout.strip()}")
        
        # Docker version
        exit_code, stdout, stderr = ssh_executor.execute_command("docker --version")
        if exit_code == 0:
            print_result(f"Version: {stdout.strip()}")
    else:
        print_error("Docker not found in PATH")
        return
    
    print_check("Docker Service Status")
    exit_code, stdout, stderr = ssh_executor.execute_command("systemctl is-active docker")
    if exit_code == 0 and 'active' in stdout:
        print_success("Docker service is active")
    else:
        print_error(f"Docker service status: {stdout.strip()}")
        print_result("Checking service details...")
        exit_code, stdout, stderr = ssh_executor.execute_command("systemctl status docker --no-pager")
        print(stdout)
    
    print_check("Docker Daemon Permissions")
    exit_code, stdout, stderr = ssh_executor.execute_command("docker ps 2>&1")
    if exit_code == 0:
        print_success("Docker permissions OK")
    else:
        print_error("Docker permission issue detected")
        print_result(stderr)
    
    # 5. Docker Images
    print_section("Docker Images")
    
    print_check("Available Images")
    exit_code, stdout, stderr = ssh_executor.execute_command("docker images")
    if exit_code == 0:
        print(stdout)
        if 'zaproxy' in stdout or 'zap' in stdout.lower():
            print_success("ZAP image found")
        else:
            print_warning("ZAP image not found")
            print_result("Attempting to pull ZAP image...")
            exit_code, stdout, stderr = ssh_executor.execute_command(
                "docker pull ghcr.io/zaproxy/zaproxy:stable 2>&1"
            )
            print(stdout)
    else:
        print_error(f"Failed to list images: {stderr}")
    
    # 6. Docker Containers
    print_section("Docker Containers")
    
    print_check("Running Containers")
    exit_code, stdout, stderr = ssh_executor.execute_command("docker ps")
    if exit_code == 0:
        print(stdout)
        if 'zap' in stdout.lower():
            print_success("ZAP container is running")
        else:
            print_warning("No ZAP container running")
    else:
        print_error(f"Failed to list containers: {stderr}")
    
    print_check("All Containers (including stopped)")
    exit_code, stdout, stderr = ssh_executor.execute_command("docker ps -a")
    if exit_code == 0:
        print(stdout)
    
    print_check("Container Logs (if exists)")
    exit_code, stdout, stderr = ssh_executor.execute_command(
        "docker logs zap-scanner 2>&1 | tail -50"
    )
    if exit_code == 0:
        print("Last 50 lines of ZAP container logs:")
        print(stdout)
    else:
        print_result("No zap-scanner container found or no logs available")
    
    # 7. Network Connectivity
    print_section("Network Connectivity")
    
    print_check("Internet Connectivity")
    exit_code, stdout, stderr = ssh_executor.execute_command("ping -c 3 8.8.8.8")
    if exit_code == 0:
        print_success("Internet connectivity OK")
    else:
        print_error("No internet connectivity")
    
    print_check("DNS Resolution")
    exit_code, stdout, stderr = ssh_executor.execute_command("nslookup google.com")
    if exit_code == 0:
        print_success("DNS resolution working")
    else:
        print_error("DNS resolution failed")
    
    print_check("Docker Hub Access")
    exit_code, stdout, stderr = ssh_executor.execute_command("curl -I https://ghcr.io 2>&1 | head -5")
    if exit_code == 0:
        print_success("Can reach GitHub Container Registry")
        print(stdout)
    else:
        print_error("Cannot reach GitHub Container Registry")
    
    # 8. ZAP Directories
    print_section("ZAP Directories")
    
    print_check("ZAP Config Directory")
    exit_code, stdout, stderr = ssh_executor.execute_command("ls -la /opt/zap/config/ 2>&1")
    if exit_code == 0:
        print(stdout)
    else:
        print_warning("ZAP config directory not found or empty")
        print_result(stderr)
    
    print_check("ZAP Reports Directory")
    exit_code, stdout, stderr = ssh_executor.execute_command("ls -la /opt/zap/reports/ 2>&1")
    if exit_code == 0:
        print(stdout)
    else:
        print_warning("ZAP reports directory not found or empty")
    
    # 9. Ports
    print_section("Port Status")
    
    print_check("Listening Ports")
    exit_code, stdout, stderr = ssh_executor.execute_command("ss -tulnp | grep -E ':(8080|22)'")
    if exit_code == 0:
        print(stdout)
        if '8080' in stdout:
            print_success("Port 8080 is listening")
        else:
            print_warning("Port 8080 not listening")
    
    # 10. User Data Status
    print_section("Instance Initialization")
    
    print_check("Cloud-init Status")
    exit_code, stdout, stderr = ssh_executor.execute_command("cloud-init status 2>&1")
    if exit_code == 0:
        print(stdout)
        if 'done' in stdout.lower():
            print_success("Cloud-init completed")
        else:
            print_warning("Cloud-init may still be running")
    
    print_check("ZAP Ready Flag")
    exit_code, stdout, stderr = ssh_executor.execute_command("ls -la /tmp/zap-ready 2>&1")
    if exit_code == 0:
        print_success("ZAP ready flag exists")
        print(stdout)
    else:
        print_warning("ZAP ready flag not found - initialization may not be complete")
    
    # 11. System Logs
    print_section("System Logs (last 30 lines)")
    
    print_check("Cloud-init Logs")
    exit_code, stdout, stderr = ssh_executor.execute_command("tail -30 /var/log/cloud-init-output.log 2>&1")
    if exit_code == 0:
        print(stdout)
    
    print_check("Docker Service Logs")
    exit_code, stdout, stderr = ssh_executor.execute_command("journalctl -u docker --no-pager -n 30")
    if exit_code == 0:
        print(stdout)
    
    # 12. Recommendations
    print_section("Diagnostic Summary & Recommendations")
    
    # Run a final check
    exit_code, stdout, stderr = ssh_executor.execute_command(
        "docker ps | grep zap-scanner"
    )
    
    if exit_code == 0:
        print_success("✅ ZAP container is running!")
        print_result("If you're still having issues, check the ZAP API at http://<ip>:8080")
    else:
        print_error("❌ ZAP container is NOT running")
        print("\nTroubleshooting steps:")
        print("  1. Check if Docker service is active (systemctl status docker)")
        print("  2. Verify ZAP image is pulled (docker images)")
        print("  3. Check cloud-init completion (cloud-init status)")
        print("  4. Review Docker logs (journalctl -u docker)")
        print("  5. Try manually starting ZAP container:")
        print("     docker run -d --name zap-scanner -p 8080:8080 \\")
        print("       ghcr.io/zaproxy/zaproxy:stable zap.sh -daemon -port 8080 \\")
        print("       -config api.key=kast01 \\")
        print("       -config api.addrs.addr.name=.* \\")
        print("       -config api.addrs.addr.regex=true")
    
    print_header("Diagnostic Complete")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Diagnose infrastructure and Docker/ZAP issues',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python diagnose_infrastructure.py /path/to/infrastructure_state.txt

This will:
  - Check system resources (disk, memory)
  - Verify Docker installation and status
  - Check Docker images and containers
  - Test network connectivity
  - Examine logs
  - Provide troubleshooting recommendations
        '''
    )
    parser.add_argument(
        'state_file',
        help='Path to infrastructure state file from test_infrastructure_provision.py'
    )
    
    args = parser.parse_args()
    
    # Load state
    print("Loading infrastructure state...")
    state = load_infrastructure_state(args.state_file)
    
    public_ip = state.get('public_ip')
    ssh_user = state.get('ssh_user')
    ssh_key = state.get('SSH Key')
    
    if not all([public_ip, ssh_user, ssh_key]):
        print_error("Missing required information in state file")
        sys.exit(1)
    
    print(f"Connecting to: {public_ip}")
    print(f"SSH User: {ssh_user}")
    print(f"SSH Key: {ssh_key}")
    
    # Connect via SSH
    ssh_executor = SSHExecutor(
        host=public_ip,
        user=ssh_user,
        private_key_path=ssh_key,
        timeout=30,
        retry_attempts=3,
        debug_callback=lambda msg: None  # Suppress debug output
    )
    
    if not ssh_executor.connect():
        print_error("Failed to establish SSH connection")
        print("\nTroubleshooting:")
        print("  1. Verify instance is running in cloud console")
        print("  2. Check security group allows SSH (port 22)")
        print("  3. Verify SSH key file permissions (should be 600)")
        print(f"  4. Try manually: ssh -i {ssh_key} {ssh_user}@{public_ip}")
        sys.exit(1)
    
    print_success("SSH connection established\n")
    
    try:
        # Run diagnostic
        run_diagnostic(ssh_executor)
    finally:
        ssh_executor.close()
    
    sys.exit(0)


if __name__ == '__main__':
    main()
