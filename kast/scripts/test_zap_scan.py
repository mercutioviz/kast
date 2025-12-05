#!/usr/bin/env python3
"""
Test script for running ZAP scan on provisioned infrastructure
Uses the ZAP automation framework with a target URL

Usage:
    python test_zap_scan.py /path/to/infrastructure_state.txt https://example.com
"""

import sys
import os
import yaml
import argparse
import tempfile
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ssh_executor import SSHExecutor
from scripts.zap_api_client import ZAPAPIClient


def print_header(message):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70 + "\n")


def print_step(step_num, message):
    """Print formatted step"""
    print(f"\n[Step {step_num}] {message}")
    print("-" * 70)


def print_success(message):
    """Print success message"""
    print(f"\n✓ SUCCESS: {message}\n")


def print_error(message):
    """Print error message"""
    print(f"\n✗ ERROR: {message}\n")


def print_info(message):
    """Print info message"""
    print(f"  → {message}")


def print_progress(message):
    """Print progress message"""
    print(f"  ⟳ {message}")


def load_infrastructure_state(state_file):
    """
    Load infrastructure state from file
    
    :param state_file: Path to state file
    :return: Dictionary with infrastructure info
    """
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


def load_cloud_config():
    """Load cloud configuration from YAML file"""
    config_path = Path(__file__).parent.parent / "config" / "zap_cloud_config.yaml"
    
    if not config_path.exists():
        print_error(f"Cloud config not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    return config


def prepare_automation_plan(target_url, config):
    """
    Prepare ZAP automation plan with target URL
    
    :param target_url: Target URL to scan
    :param config: Cloud configuration
    :return: Path to temporary plan file
    """
    automation_plan_path = Path(config.get('zap_config', {}).get('automation_plan', ''))
    
    if not automation_plan_path.exists():
        # Try relative to config directory
        automation_plan_path = Path(__file__).parent.parent / "config" / "zap_automation_plan.yaml"
    
    if not automation_plan_path.exists():
        print_error(f"Automation plan not found: {automation_plan_path}")
        sys.exit(1)
    
    # Read and substitute target URL
    with open(automation_plan_path, 'r') as f:
        plan_content = f.read()
    
    plan_content = plan_content.replace('${TARGET_URL}', target_url)
    
    # Write to temporary file
    temp_plan = Path(tempfile.gettempdir()) / f'zap_plan_{datetime.now().strftime("%Y%m%d_%H%M%S")}.yaml'
    with open(temp_plan, 'w') as f:
        f.write(plan_content)
    
    return temp_plan


def start_zap_container(ssh_executor, config, plan_path):
    """
    Start ZAP Docker container with automation framework
    
    :param ssh_executor: SSH executor instance
    :param config: Cloud configuration
    :param plan_path: Path to automation plan on remote host
    :return: True if successful
    """
    print_info("Starting ZAP Docker container...")
    
    zap_config = config.get('zap_config', {})
    docker_image = zap_config.get('docker_image')
    api_port = zap_config.get('api_port', 8080)
    api_key = zap_config.get('api_key', 'kast01')
    
    # Stop any existing ZAP container
    ssh_executor.execute_command("docker stop zap-scanner 2>/dev/null || true")
    ssh_executor.execute_command("docker rm zap-scanner 2>/dev/null || true")
    
    # Start ZAP container with automation framework and API key
    container_cmd = f"""docker run -d \\
  --name zap-scanner \\
  -p {api_port}:8080 \\
  -v /opt/zap/config:/zap/config \\
  -v /opt/zap/reports:/zap/reports \\
  {docker_image} \\
  zap.sh -daemon -port 8080 \\
  -config api.key={api_key} \\
  -config api.addrs.addr.name=.* \\
  -config api.addrs.addr.regex=true \\
  -autorun /zap/config/automation_plan.yaml"""
    
    exit_code, stdout, stderr = ssh_executor.execute_command(container_cmd)
    
    if exit_code == 0:
        container_id = stdout.strip()
        print_success(f"ZAP container started: {container_id[:12]}")
        return True
    else:
        print_error(f"Failed to start ZAP container: {stderr}")
        return False


def run_zap_scan(state_file, target_url):
    """
    Run ZAP scan on provisioned infrastructure
    
    :param state_file: Path to infrastructure state file
    :param target_url: Target URL to scan
    :return: True if successful
    """
    print_header(f"ZAP Scan Test - {target_url}")
    
    try:
        # Step 1: Load infrastructure state
        print_step(1, "Loading infrastructure state")
        state = load_infrastructure_state(state_file)
        
        public_ip = state.get('public_ip')
        ssh_user = state.get('ssh_user')
        ssh_key = state.get('SSH Key')
        
        if not all([public_ip, ssh_user, ssh_key]):
            print_error("Missing required information in state file")
            return False
        
        print_info(f"Public IP: {public_ip}")
        print_info(f"SSH User: {ssh_user}")
        print_success("State loaded")
        
        # Step 2: Load cloud configuration
        print_step(2, "Loading cloud configuration")
        config = load_cloud_config()
        zap_config = config.get('zap_config', {})
        print_success("Configuration loaded")
        
        # Step 3: Prepare automation plan
        print_step(3, "Preparing ZAP automation plan")
        local_plan = prepare_automation_plan(target_url, config)
        print_info(f"Automation plan created: {local_plan}")
        print_success("Plan ready")
        
        # Step 4: Connect via SSH
        print_step(4, "Connecting to instance via SSH")
        ssh_executor = SSHExecutor(
            host=public_ip,
            user=ssh_user,
            private_key_path=ssh_key,
            timeout=zap_config.get('ssh_timeout_seconds', 300),
            retry_attempts=zap_config.get('ssh_retry_attempts', 5),
            debug_callback=print_info
        )
        
        if not ssh_executor.connect():
            print_error("SSH connection failed")
            local_plan.unlink()
            return False
        
        print_success("SSH connected")
        
        # Step 5: Upload automation plan
        print_step(5, "Uploading automation plan to instance")
        remote_plan = '/opt/zap/config/automation_plan.yaml'
        
        # Ensure directory exists
        ssh_executor.execute_command('mkdir -p /opt/zap/config /opt/zap/reports')
        ssh_executor.execute_command('chmod -R 777 /opt/zap')
        
        ssh_executor.upload_file(str(local_plan), remote_plan)
        local_plan.unlink()  # Clean up local temp file
        
        print_success("Plan uploaded")
        
        # Step 6: Start ZAP container
        print_step(6, "Starting ZAP Docker container")
        if not start_zap_container(ssh_executor, config, remote_plan):
            ssh_executor.close()
            return False
        
        # Step 7: Wait for ZAP to be ready
        print_step(7, "Waiting for ZAP to be ready")
        zap_api_url = f"http://{public_ip}:{zap_config.get('api_port', 8080)}"
        zap_client = ZAPAPIClient(
            api_url=zap_api_url,
            api_key=zap_config.get('api_key'),
            debug_callback=print_info
        )
        
        if not zap_client.wait_for_ready(timeout=300):
            print_error("ZAP failed to become ready")
            ssh_executor.close()
            return False
        
        print_success("ZAP is ready")
        
        # Step 8: Monitor scan progress
        print_step(8, "Monitoring scan progress")
        timeout_minutes = zap_config.get('timeout_minutes', 60)
        poll_interval = zap_config.get('poll_interval_seconds', 30)
        
        print_info(f"Scan timeout: {timeout_minutes} minutes")
        print_info(f"Poll interval: {poll_interval} seconds")
        print_info(f"Target: {target_url}")
        print()
        
        if not zap_client.wait_for_scan_completion(timeout=timeout_minutes*60, poll_interval=poll_interval):
            print_error("Scan timeout")
            ssh_executor.close()
            return False
        
        print_success("Scan completed")
        
        # Step 9: Download results
        print_step(9, "Downloading scan results")
        
        # Create results directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_dir = Path(__file__).parent.parent.parent / "test_output" / f"zap_scan_{timestamp}"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        report_name = zap_config.get('report_name', 'zap_report.json')
        remote_report = f'/opt/zap/reports/{report_name}'
        local_report = results_dir / report_name
        
        ssh_executor.download_file(remote_report, str(local_report))
        print_success(f"Results saved to: {local_report}")
        
        # Step 10: Display summary
        print_step(10, "Scan summary")
        
        # Try to parse and display basic stats
        try:
            import json
            with open(local_report, 'r') as f:
                results = json.load(f)
            
            if 'site' in results and isinstance(results['site'], list):
                for site in results['site']:
                    alerts = site.get('alerts', [])
                    print_info(f"Total alerts: {len(alerts)}")
                    
                    # Count by risk
                    risk_counts = {}
                    for alert in alerts:
                        risk = alert.get('riskdesc', 'Unknown').split()[0]
                        risk_counts[risk] = risk_counts.get(risk, 0) + 1
                    
                    for risk, count in sorted(risk_counts.items()):
                        print_info(f"  {risk}: {count}")
        except Exception as e:
            print_info(f"Could not parse results: {e}")
        
        # Cleanup
        ssh_executor.close()
        
        # Success summary
        print_header("Scan Complete")
        print_success("ZAP scan finished successfully")
        print_info(f"Results directory: {results_dir}")
        print_info(f"Report file: {local_report}")
        print()
        print("=" * 70)
        print("  Note: Infrastructure is still running!")
        print(f"  Use test_infrastructure_teardown.py to clean up:")
        print(f"  python test_infrastructure_teardown.py {state_file}")
        print("=" * 70 + "\n")
        
        return True
        
    except KeyboardInterrupt:
        print_error("Scan interrupted by user")
        return False
    except Exception as e:
        print_error(f"Scan failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Test ZAP scan on provisioned infrastructure',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # After provisioning infrastructure with test_infrastructure_provision.py
  python test_zap_scan.py /opt/kast/test_output/infra_test_aws_20251126_200617/infrastructure_state.txt https://example.com

Note: 
  - Infrastructure must already be provisioned
  - The automation plan will be uploaded and executed
  - Results will be downloaded to test_output/zap_scan_TIMESTAMP/
        '''
    )
    parser.add_argument(
        'state_file',
        help='Path to infrastructure state file from test_infrastructure_provision.py'
    )
    parser.add_argument(
        'target_url',
        help='Target URL to scan (e.g., https://example.com)'
    )
    
    args = parser.parse_args()
    
    # Validate state file exists
    if not Path(args.state_file).exists():
        print_error(f"State file not found: {args.state_file}")
        sys.exit(1)
    
    # Validate target URL format
    if not args.target_url.startswith(('http://', 'https://')):
        print_error("Target URL must start with http:// or https://")
        sys.exit(1)
    
    # Run scan
    success = run_zap_scan(args.state_file, args.target_url)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)
