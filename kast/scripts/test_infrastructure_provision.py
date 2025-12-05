#!/usr/bin/env python3
"""
Test script for provisioning cloud infrastructure
Tests the Terraform provisioning process without running ZAP scan

Usage:
    python test_infrastructure_provision.py aws
    python test_infrastructure_provision.py azure
    python test_infrastructure_provision.py gcp
"""

import sys
import os
import yaml
import argparse
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.terraform_manager import TerraformManager


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


def generate_ssh_keypair(output_dir):
    """
    Generate SSH keypair for instance access
    
    :param output_dir: Directory to store keys
    :return: Tuple of (private_key_path, public_key_string)
    """
    print_info("Generating SSH keypair...")
    
    # Generate RSA key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # Get public key
    public_key = private_key.public_key()
    
    # Serialize private key
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # Serialize public key
    public_openssh = public_key.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH
    )
    
    # Save private key
    key_path = Path(output_dir) / "test_ssh_key"
    with open(key_path, 'wb') as f:
        f.write(private_pem)
    key_path.chmod(0o600)
    
    # Save public key
    pub_key_path = Path(output_dir) / "test_ssh_key.pub"
    with open(pub_key_path, 'wb') as f:
        f.write(public_openssh)
    
    public_key_str = public_openssh.decode('utf-8')
    
    print_info(f"SSH keypair saved to: {key_path}")
    return str(key_path), public_key_str


def expand_env_vars(obj):
    """
    Recursively expand environment variables in config
    
    :param obj: Configuration object (dict, list, or str)
    :return: Expanded object
    """
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [expand_env_vars(item) for item in obj]
    elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
        env_var = obj[2:-1]
        value = os.environ.get(env_var)
        if value is None:
            # Return the original placeholder if env var not set
            # Will validate required vars later for selected provider
            return obj
        return value
    return obj


def load_cloud_config():
    """Load cloud configuration from YAML file"""
    config_path = Path(__file__).parent.parent / "config" / "zap_cloud_config.yaml"
    
    if not config_path.exists():
        print_error(f"Cloud config not found: {config_path}")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Expand environment variables
    config = expand_env_vars(config)
    
    return config


def get_terraform_variables(provider, config, ssh_public_key):
    """
    Build Terraform variables dictionary for provider
    
    :param provider: Cloud provider name
    :param config: Cloud configuration
    :param ssh_public_key: SSH public key string
    :return: Variables dictionary
    """
    provider_config = config.get(provider, {})
    zap_config = config.get('zap_config', {})
    tags = config.get('tags', {})
    
    if provider == 'aws':
        return {
            'region': provider_config.get('region', 'us-east-1'),
            'access_key_id': provider_config.get('access_key_id'),
            'secret_access_key': provider_config.get('secret_access_key'),
            'instance_type': provider_config.get('instance_type', 't3.medium'),
            'ami_id': provider_config.get('ami_id', ''),
            'spot_max_price': provider_config.get('spot_max_price', '0.05'),
            'ssh_public_key': ssh_public_key,
            'zap_docker_image': zap_config.get('docker_image'),
            'tags': tags
        }
    elif provider == 'azure':
        return {
            'subscription_id': provider_config.get('subscription_id'),
            'tenant_id': provider_config.get('tenant_id'),
            'client_id': provider_config.get('client_id'),
            'client_secret': provider_config.get('client_secret'),
            'region': provider_config.get('region', 'eastus'),
            'vm_size': provider_config.get('vm_size', 'Standard_B2s'),
            'spot_enabled': provider_config.get('spot_enabled', True),
            'spot_max_price': provider_config.get('spot_max_price', -1),
            'ssh_public_key': ssh_public_key,
            'zap_docker_image': zap_config.get('docker_image'),
            'tags': tags
        }
    elif provider == 'gcp':
        return {
            'project_id': provider_config.get('project_id'),
            'credentials_file': provider_config.get('credentials_file'),
            'region': provider_config.get('region', 'us-central1'),
            'zone': provider_config.get('zone', 'us-central1-a'),
            'machine_type': provider_config.get('machine_type', 'n1-standard-2'),
            'preemptible': provider_config.get('preemptible', True),
            'ssh_public_key': ssh_public_key,
            'zap_docker_image': zap_config.get('docker_image'),
            'labels': {k.lower().replace('_', '-'): v.lower() for k, v in tags.items()}
        }
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def provision_infrastructure(provider):
    """
    Provision cloud infrastructure for specified provider
    
    :param provider: Cloud provider (aws, azure, gcp)
    :return: Tuple of (success, outputs, state_info_path)
    """
    print_header(f"Infrastructure Provisioning Test - {provider.upper()}")
    
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path(__file__).parent.parent.parent / "test_output" / f"infra_test_{provider}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print_info(f"Output directory: {output_dir}")
    
    try:
        # Step 1: Load configuration
        print_step(1, "Loading cloud configuration")
        config = load_cloud_config()
        print_info(f"Configuration loaded for provider: {provider}")
        
        # Step 2: Generate SSH keypair
        print_step(2, "Generating SSH keypair")
        ssh_key_path, ssh_public_key = generate_ssh_keypair(output_dir)
        print_success("SSH keypair generated")
        
        # Step 3: Prepare Terraform variables
        print_step(3, "Preparing Terraform variables")
        tf_vars = get_terraform_variables(provider, config, ssh_public_key)
        print_info(f"Variables prepared for {provider}")
        
        # Step 4: Initialize Terraform manager
        print_step(4, "Initializing Terraform manager")
        terraform_module_dir = Path(__file__).parent.parent / "terraform" / provider
        if not terraform_module_dir.exists():
            print_error(f"Terraform module not found: {terraform_module_dir}")
            return False, None, None
        
        def debug_callback(msg):
            print_info(msg)
        
        tf_manager = TerraformManager(provider, output_dir, debug_callback)
        print_success("Terraform manager initialized")
        
        # Step 5: Provision infrastructure
        print_step(5, "Provisioning infrastructure (this may take several minutes)")
        print_info("Running: terraform init → plan → apply")
        
        success, outputs = tf_manager.provision(terraform_module_dir, tf_vars, timeout=900)
        
        if not success:
            print_error("Infrastructure provisioning failed")
            return False, None, None
        
        print_success("Infrastructure provisioned successfully")
        
        # Step 6: Display outputs
        print_step(6, "Infrastructure outputs")
        for key, value in outputs.items():
            print_info(f"{key}: {value}")
        
        # Step 7: Save state information
        print_step(7, "Saving state information")
        state_info_path = output_dir / "infrastructure_state.txt"
        with open(state_info_path, 'w') as f:
            f.write(f"Provider: {provider}\n")
            f.write(f"Timestamp: {timestamp}\n")
            f.write(f"Terraform Directory: {tf_manager.terraform_dir}\n")
            f.write(f"SSH Key: {ssh_key_path}\n")
            f.write(f"\nOutputs:\n")
            for key, value in outputs.items():
                f.write(f"  {key}: {value}\n")
        
        print_info(f"State information saved to: {state_info_path}")
        
        # Success summary
        print_header("Provisioning Complete")
        print_success(f"{provider.upper()} infrastructure is running")
        print_info(f"Public IP: {outputs.get('public_ip', 'N/A')}")
        print_info(f"SSH User: {outputs.get('ssh_user', 'N/A')}")
        print_info(f"ZAP API URL: {outputs.get('zap_api_url', 'N/A')}")
        print("\n" + "=" * 70)
        print("  IMPORTANT: Remember to run the teardown script to cleanup!")
        print(f"  python test_infrastructure_teardown.py {state_info_path}")
        print("=" * 70 + "\n")
        
        return True, outputs, str(state_info_path)
        
    except KeyboardInterrupt:
        print_error("Provisioning interrupted by user")
        return False, None, None
    except Exception as e:
        print_error(f"Provisioning failed: {e}")
        import traceback
        traceback.print_exc()
        return False, None, None


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Test infrastructure provisioning for ZAP Cloud Plugin',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python test_infrastructure_provision.py aws
  python test_infrastructure_provision.py azure
  python test_infrastructure_provision.py gcp

Note: Make sure to set required environment variables for the chosen provider.
        '''
    )
    parser.add_argument(
        'provider',
        choices=['aws', 'azure', 'gcp'],
        help='Cloud provider to test (aws, azure, or gcp)'
    )
    
    args = parser.parse_args()
    
    # Provision infrastructure
    success, outputs, state_info_path = provision_infrastructure(args.provider)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
