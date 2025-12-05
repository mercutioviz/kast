"""
File: plugins/zap_plugin.py
Description: KAST plugin for OWASP ZAP with cloud infrastructure provisioning
"""

import subprocess
import shutil
import json
import os
import yaml
import tempfile
from datetime import datetime
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from kast.plugins.base import KastPlugin
from kast.scripts.terraform_manager import TerraformManager
from kast.scripts.ssh_executor import SSHExecutor
from kast.scripts.zap_api_client import ZAPAPIClient


class ZapPlugin(KastPlugin):
    priority = 200  # Run later (higher number = lower priority)

    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "zap"
        self.display_name = "OWASP ZAP"
        self.description = "OWASP ZAP Active Scanner with Cloud Infrastructure"
        self.website_url = "https://www.zaproxy.org/"
        self.scan_type = "active"
        self.output_type = "file"
        
        # Cloud infrastructure components
        self.terraform_manager = None
        self.ssh_executor = None
        self.zap_client = None
        self.cloud_config = None
        self.infrastructure_outputs = None
        self.ssh_key_path = None
        self.ssh_public_key = None

    def setup(self, target, output_dir):
        """Setup before run"""
        self.debug("Setup completed.")

    def is_available(self):
        """Check if Terraform is installed"""
        return shutil.which("terraform") is not None

    def _load_cloud_config(self):
        """
        Load cloud configuration from YAML file
        
        :return: Configuration dictionary
        """
        config_path = Path(__file__).parent.parent / "config" / "zap_cloud_config.yaml"
        
        if not config_path.exists():
            raise FileNotFoundError(f"Cloud config not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Expand environment variables
        config = self._expand_env_vars(config)
        
        self.debug(f"Loaded cloud config for provider: {config.get('cloud_provider')}")
        return config

    def _expand_env_vars(self, obj):
        """
        Recursively expand environment variables in config
        
        :param obj: Configuration object (dict, list, or str)
        :return: Expanded object
        """
        if isinstance(obj, dict):
            return {k: self._expand_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._expand_env_vars(item) for item in obj]
        elif isinstance(obj, str) and obj.startswith('${') and obj.endswith('}'):
            # Extract env var name and expand
            env_var = obj[2:-1]
            return os.environ.get(env_var, obj)
        return obj

    def _generate_ssh_keypair(self, output_dir):
        """
        Generate SSH keypair for instance access
        
        :param output_dir: Directory to store keys
        :return: Tuple of (private_key_path, public_key_string)
        """
        self.debug("Generating SSH keypair...")
        
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
        key_path = Path(output_dir) / "zap_ssh_key"
        with open(key_path, 'wb') as f:
            f.write(private_pem)
        key_path.chmod(0o600)
        
        # Save public key
        pub_key_path = Path(output_dir) / "zap_ssh_key.pub"
        with open(pub_key_path, 'wb') as f:
            f.write(public_openssh)
        
        public_key_str = public_openssh.decode('utf-8')
        
        self.debug(f"SSH keypair generated: {key_path}")
        return str(key_path), public_key_str

    def _get_terraform_variables(self, provider, config, ssh_public_key):
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
            # AWS credentials are resolved automatically by Terraform via:
            # 1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
            # 2. AWS CLI credentials (~/.aws/credentials)
            # 3. IAM instance profiles
            return {
                'region': provider_config.get('region', 'us-east-1'),
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

    def _start_zap_container(self, target_url):
        """
        Start ZAP Docker container with automation framework
        
        :param target_url: Target URL to scan
        :return: True if successful
        """
        self.debug("Starting ZAP Docker container...")
        
        zap_config = self.cloud_config.get('zap_config', {})
        docker_image = zap_config.get('docker_image')
        api_port = zap_config.get('api_port', 8080)
        api_key = zap_config.get('api_key', 'kast01')
        
        # Prepare automation plan with target URL
        automation_plan = Path(zap_config.get('automation_plan'))
        
        # Read and substitute target URL
        with open(automation_plan, 'r') as f:
            plan_content = f.read()
        plan_content = plan_content.replace('${TARGET_URL}', target_url)
        
        # Upload modified plan
        remote_plan_path = '/opt/zap/config/automation_plan.yaml'
        local_temp_plan = Path(tempfile.gettempdir()) / 'zap_plan_temp.yaml'
        with open(local_temp_plan, 'w') as f:
            f.write(plan_content)
        
        self.ssh_executor.upload_file(local_temp_plan, remote_plan_path)
        local_temp_plan.unlink()
        
        # Start ZAP container with automation framework and API key
        container_cmd = f"""
        docker run -d \\
          --name zap-scanner \\
          -p {api_port}:8080 \\
          -v /opt/zap/config:/zap/config \\
          -v /opt/zap/reports:/zap/reports \\
          {docker_image} \\
          zap.sh -daemon -port 8080 \\
          -config api.key={api_key} \\
          -config api.addrs.addr.name=.* \\
          -config api.addrs.addr.regex=true \\
          -autorun /zap/config/automation_plan.yaml
        """
        
        exit_code, stdout, stderr = self.ssh_executor.execute_command(container_cmd)
        
        if exit_code == 0:
            self.debug("ZAP container started successfully")
            return True
        else:
            self.debug(f"Failed to start ZAP container: {stderr}")
            return False

    def run(self, target, output_dir, report_only):
        """Run ZAP scan with cloud infrastructure"""
        self.setup(target, output_dir)
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
        
        if report_only:
            # In report-only mode, check for existing results
            output_file = os.path.join(output_dir, f"{self.name}.json")
            if os.path.exists(output_file):
                with open(output_file, "r") as f:
                    results = json.load(f)
                return self.get_result_dict("success", results, timestamp)
            else:
                return self.get_result_dict("fail", "No existing results found", timestamp)
        
        try:
            # Load cloud configuration
            self.cloud_config = self._load_cloud_config()
            provider = self.cloud_config.get('cloud_provider')
            
            self.debug(f"Using cloud provider: {provider}")
            
            # Generate SSH keypair
            self.ssh_key_path, self.ssh_public_key = self._generate_ssh_keypair(output_dir)
            
            # Prepare Terraform variables
            tf_vars = self._get_terraform_variables(provider, self.cloud_config, self.ssh_public_key)
            
            # Initialize Terraform manager
            terraform_module_dir = Path(__file__).parent.parent / "terraform" / provider
            self.terraform_manager = TerraformManager(provider, Path(output_dir), self.debug)
            
            # Provision infrastructure
            self.debug("Provisioning cloud infrastructure...")
            success, outputs = self.terraform_manager.provision(terraform_module_dir, tf_vars, timeout=900)
            
            if not success:
                return self.get_result_dict("fail", "Infrastructure provisioning failed", timestamp)
            
            self.infrastructure_outputs = outputs
            public_ip = outputs.get('public_ip')
            ssh_user = outputs.get('ssh_user')
            
            self.debug(f"Infrastructure provisioned: {public_ip}")
            
            # Connect via SSH
            self.ssh_executor = SSHExecutor(
                host=public_ip,
                user=ssh_user,
                private_key_path=self.ssh_key_path,
                timeout=self.cloud_config.get('zap_config', {}).get('ssh_timeout_seconds', 300),
                retry_attempts=self.cloud_config.get('zap_config', {}).get('ssh_retry_attempts', 5),
                debug_callback=self.debug
            )
            
            if not self.ssh_executor.connect():
                self._cleanup_on_failure()
                return self.get_result_dict("fail", "SSH connection failed", timestamp)
            
            # Wait for instance readiness
            if not self.ssh_executor.wait_for_file('/tmp/zap-ready', timeout=300):
                self._cleanup_on_failure()
                return self.get_result_dict("fail", "Instance not ready", timestamp)
            
            # Start ZAP container
            if not self._start_zap_container(target):
                self._cleanup_on_failure()
                return self.get_result_dict("fail", "Failed to start ZAP", timestamp)
            
            # Initialize ZAP API client
            zap_api_url = outputs.get('zap_api_url')
            self.zap_client = ZAPAPIClient(
                api_url=zap_api_url,
                api_key=self.cloud_config.get('zap_config', {}).get('api_key'),
                debug_callback=self.debug
            )
            
            # Wait for ZAP to be ready
            if not self.zap_client.wait_for_ready(timeout=300):
                self._cleanup_on_failure()
                return self.get_result_dict("fail", "ZAP not ready", timestamp)
            
            # Monitor scan progress
            timeout_minutes = self.cloud_config.get('zap_config', {}).get('timeout_minutes', 60)
            poll_interval = self.cloud_config.get('zap_config', {}).get('poll_interval_seconds', 30)
            
            if not self.zap_client.wait_for_scan_completion(timeout=timeout_minutes*60, poll_interval=poll_interval):
                self._cleanup_on_failure()
                return self.get_result_dict("fail", "Scan timeout", timestamp)
            
            # Download results
            remote_report = f"/opt/zap/reports/{self.cloud_config.get('zap_config', {}).get('report_name', 'zap_report.json')}"
            local_report = os.path.join(output_dir, f"{self.name}.json")
            
            self.ssh_executor.download_file(remote_report, local_report)
            
            # Load results
            with open(local_report, 'r') as f:
                results = json.load(f)
            
            # Teardown infrastructure
            self.debug("Tearing down infrastructure...")
            self.ssh_executor.close()
            self.terraform_manager.teardown(timeout=600)
            
            return self.get_result_dict("success", results, timestamp)
            
        except Exception as e:
            self.debug(f"ZAP plugin failed: {e}")
            self._cleanup_on_failure()
            return self.get_result_dict("fail", str(e), timestamp)

    def _cleanup_on_failure(self):
        """Cleanup resources on failure"""
        try:
            if self.ssh_executor:
                self.ssh_executor.close()
            if self.terraform_manager:
                self.terraform_manager.teardown(timeout=600)
        except Exception as e:
            self.debug(f"Cleanup error: {e}")

    def post_process(self, raw_output, output_dir):
        """Post-process ZAP results"""
        # Load findings
        if isinstance(raw_output, str) and os.path.isfile(raw_output):
            with open(raw_output, "r") as f:
                findings = json.load(f)
        elif isinstance(raw_output, dict):
            findings = raw_output.get("results", raw_output)
        else:
            findings = {}
        
        # Parse ZAP alerts
        alerts = findings.get('alerts', [])
        
        # Group by risk
        risk_counts = {'High': 0, 'Medium': 0, 'Low': 0, 'Informational': 0}
        issues = []
        
        for alert in alerts:
            risk = alert.get('risk', 'Informational')
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
            issues.append(f"{alert.get('name', 'Unknown')} [{risk}]")
        
        # Build summary
        total = sum(risk_counts.values())
        if total == 0:
            summary = "No vulnerabilities detected"
            executive_summary = "ZAP scan completed. No security issues found."
        else:
            summary = f"Found {total} issues: {risk_counts['High']} High, {risk_counts['Medium']} Medium, {risk_counts['Low']} Low"
            executive_summary = f"ZAP scan identified {total} security findings requiring attention."
        
        # Build details
        details = f"Total Alerts: {total}\n"
        for risk, count in risk_counts.items():
            if count > 0:
                details += f"  {risk}: {count}\n"
        
        processed = {
            "plugin-name": self.name,
            "plugin-description": self.description,
            "plugin-display-name": self.display_name,
            "plugin-website-url": self.website_url,
            "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
            "findings": findings,
            "summary": summary,
            "details": details,
            "issues": issues[:50],  # Limit to 50 issues
            "executive_summary": executive_summary,
            "cloud_provider": self.cloud_config.get('cloud_provider') if self.cloud_config else 'unknown',
            "infrastructure_outputs": self.infrastructure_outputs
        }
        
        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)
        
        return processed_path
