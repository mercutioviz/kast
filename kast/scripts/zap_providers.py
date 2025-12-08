"""
ZAP Instance Provider Abstraction
Supports multiple execution modes: local, remote, and cloud
"""

import os
import subprocess
import time
import tempfile
from pathlib import Path
from abc import ABC, abstractmethod
from datetime import datetime

from kast.scripts.zap_api_client import ZAPAPIClient


class ZapInstanceProvider(ABC):
    """Abstract base class for ZAP instance providers"""
    
    def __init__(self, config, debug_callback=None):
        """
        Initialize provider
        
        :param config: Configuration dictionary
        :param debug_callback: Optional callback for debug messages
        """
        self.config = config
        self.debug = debug_callback or (lambda x: None)
        self.zap_client = None
        self.instance_info = {}
    
    @abstractmethod
    def provision(self, target_url, output_dir):
        """
        Provision/initialize ZAP instance
        
        :param target_url: Target URL to scan
        :param output_dir: Directory for output files
        :return: Tuple of (success: bool, zap_client: ZAPAPIClient, instance_info: dict)
        """
        pass
    
    @abstractmethod
    def upload_automation_plan(self, plan_content, target_url):
        """
        Upload automation plan to ZAP instance
        
        :param plan_content: YAML content of automation plan
        :param target_url: Target URL to scan
        :return: True if successful
        """
        pass
    
    @abstractmethod
    def download_results(self, output_dir, report_name):
        """
        Download scan results from ZAP instance
        
        :param output_dir: Local directory to save results
        :param report_name: Name of report file
        :return: Path to downloaded file or None
        """
        pass
    
    @abstractmethod
    def cleanup(self):
        """
        Cleanup resources (if needed)
        """
        pass
    
    @abstractmethod
    def get_mode_name(self):
        """
        Get human-readable name of this provider mode
        
        :return: Mode name (e.g., "local", "remote", "cloud")
        """
        pass


class LocalZapProvider(ZapInstanceProvider):
    """Provider for local ZAP instances (Docker or native)"""
    
    def __init__(self, config, debug_callback=None):
        super().__init__(config, debug_callback)
        self.container_name = None
        self.started_container = False
        self.temp_config_dir = None
    
    def get_mode_name(self):
        return "local"
    
    def _check_docker_available(self):
        """Check if Docker is available"""
        try:
            result = subprocess.run(['docker', '--version'], 
                                   capture_output=True, 
                                   text=True, 
                                   timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def _find_running_zap_container(self):
        """Find running ZAP container"""
        try:
            result = subprocess.run(['docker', 'ps', '--filter', 'ancestor=ghcr.io/zaproxy/zaproxy', 
                                    '--format', '{{.Names}}'],
                                   capture_output=True, 
                                   text=True, 
                                   timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                container_name = result.stdout.strip().split('\n')[0]
                self.debug(f"Found running ZAP container: {container_name}")
                return container_name
        except:
            pass
        return None
    
    def _start_zap_container(self, output_dir):
        """Start new ZAP Docker container"""
        local_config = self.config.get('local', {})
        docker_image = local_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable')
        api_port = local_config.get('api_port', 8080)
        api_key = local_config.get('api_key', 'kast-local')
        self.container_name = local_config.get('container_name', 'kast-zap-local')
        
        # Create temporary directories for ZAP
        self.temp_config_dir = Path(output_dir) / 'zap_config'
        self.temp_config_dir.mkdir(exist_ok=True)
        
        reports_dir = Path(output_dir) / 'zap_reports'
        reports_dir.mkdir(exist_ok=True)
        
        self.debug(f"Starting local ZAP container: {self.container_name}")
        
        # Start container
        cmd = [
            'docker', 'run', '-d',
            '--name', self.container_name,
            '-p', f'{api_port}:8080',
            '-v', f'{self.temp_config_dir}:/zap/config',
            '-v', f'{reports_dir}:/zap/reports',
            docker_image,
            'zap.sh', '-daemon', '-port', '8080',
            '-config', f'api.key={api_key}',
            '-config', 'api.addrs.addr.name=.*',
            '-config', 'api.addrs.addr.regex=true'
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                self.debug("ZAP container started successfully")
                self.started_container = True
                return True
            else:
                self.debug(f"Failed to start container: {result.stderr}")
                return False
        except Exception as e:
            self.debug(f"Error starting container: {e}")
            return False
    
    def provision(self, target_url, output_dir):
        """Provision local ZAP instance"""
        self.debug("Provisioning local ZAP instance...")
        
        if not self._check_docker_available():
            return False, None, {"error": "Docker not available"}
        
        local_config = self.config.get('local', {})
        api_port = local_config.get('api_port', 8080)
        api_key = local_config.get('api_key', 'kast-local')
        auto_start = local_config.get('auto_start', True)
        
        # Check for existing container
        existing_container = self._find_running_zap_container()
        
        if existing_container:
            self.debug(f"Using existing ZAP container: {existing_container}")
            self.container_name = existing_container
        elif auto_start:
            if not self._start_zap_container(output_dir):
                return False, None, {"error": "Failed to start ZAP container"}
        else:
            return False, None, {"error": "No running ZAP container found and auto_start disabled"}
        
        # Create ZAP API client
        api_url = f"http://localhost:{api_port}"
        self.zap_client = ZAPAPIClient(api_url, api_key, debug_callback=self.debug)
        
        # Wait for ZAP to be ready
        if not self.zap_client.wait_for_ready(timeout=120, poll_interval=5):
            if self.started_container:
                self._cleanup_container()
            return False, None, {"error": "ZAP not ready"}
        
        self.instance_info = {
            'mode': 'local',
            'container_name': self.container_name,
            'api_url': api_url,
            'started_by_kast': self.started_container
        }
        
        return True, self.zap_client, self.instance_info
    
    def upload_automation_plan(self, plan_content, target_url):
        """Upload automation plan to local container"""
        if not self.temp_config_dir:
            self.debug("No config directory available")
            return False
        
        # Substitute target URL
        plan_content = plan_content.replace('${TARGET_URL}', target_url)
        
        # Write plan to config directory (mounted in container)
        plan_path = self.temp_config_dir / 'automation_plan.yaml'
        with open(plan_path, 'w') as f:
            f.write(plan_content)
        
        self.debug(f"Automation plan written to {plan_path}")
        
        # Trigger automation via API
        try:
            # Use docker exec to run autorun
            cmd = [
                'docker', 'exec', self.container_name,
                'zap-cli', 'quick-scan', '--self-contained',
                '--start-options', '-config api.disablekey=true',
                target_url
            ]
            # Note: The automation framework will be triggered via the mounted plan
            # For now, we'll rely on the API-based scanning
            self.debug("Automation plan uploaded successfully")
            return True
        except Exception as e:
            self.debug(f"Error uploading plan: {e}")
            return False
    
    def download_results(self, output_dir, report_name):
        """Download results from local container"""
        try:
            # Results are already in mounted volume
            reports_dir = Path(output_dir) / 'zap_reports'
            report_path = reports_dir / report_name
            
            if report_path.exists():
                self.debug(f"Report found at {report_path}")
                return str(report_path)
            
            # If not found, generate via API
            self.debug("Generating report via API...")
            output_path = Path(output_dir) / report_name
            self.zap_client.generate_report(str(output_path), 'json')
            return str(output_path)
            
        except Exception as e:
            self.debug(f"Error downloading results: {e}")
            return None
    
    def _cleanup_container(self):
        """Stop and remove container"""
        if self.container_name and self.started_container:
            try:
                self.debug(f"Stopping container: {self.container_name}")
                subprocess.run(['docker', 'stop', self.container_name], 
                             capture_output=True, timeout=30)
                subprocess.run(['docker', 'rm', self.container_name], 
                             capture_output=True, timeout=30)
            except Exception as e:
                self.debug(f"Error stopping container: {e}")
    
    def cleanup(self):
        """Cleanup local resources"""
        local_config = self.config.get('local', {})
        cleanup_container = local_config.get('cleanup_on_completion', False)
        
        if cleanup_container:
            self._cleanup_container()
        else:
            self.debug("Keeping local ZAP container running (cleanup_on_completion=false)")


class RemoteZapProvider(ZapInstanceProvider):
    """Provider for existing remote ZAP instances"""
    
    def get_mode_name(self):
        return "remote"
    
    def provision(self, target_url, output_dir):
        """Connect to remote ZAP instance"""
        self.debug("Connecting to remote ZAP instance...")
        
        remote_config = self.config.get('remote', {})
        api_url = remote_config.get('api_url')
        api_key = remote_config.get('api_key')
        timeout = remote_config.get('timeout_seconds', 30)
        
        if not api_url:
            return False, None, {"error": "No api_url configured for remote mode"}
        
        # Expand environment variables
        api_url = os.path.expandvars(api_url)
        if api_key:
            api_key = os.path.expandvars(api_key)
        
        self.debug(f"Connecting to {api_url}")
        
        # Create ZAP API client
        self.zap_client = ZAPAPIClient(api_url, api_key, timeout=timeout, debug_callback=self.debug)
        
        # Verify connection
        if not self.zap_client.check_connection():
            return False, None, {"error": f"Cannot connect to {api_url}"}
        
        self.instance_info = {
            'mode': 'remote',
            'api_url': api_url,
            'has_api_key': bool(api_key)
        }
        
        return True, self.zap_client, self.instance_info
    
    def upload_automation_plan(self, plan_content, target_url):
        """
        For remote instances, we'll use direct API calls instead of automation plans
        since we don't have filesystem access
        """
        self.debug("Remote mode: Will use API-based scanning instead of automation plan")
        # The actual scanning will be done via API calls in the plugin
        return True
    
    def download_results(self, output_dir, report_name):
        """Download results via API"""
        try:
            output_path = Path(output_dir) / report_name
            self.zap_client.generate_report(str(output_path), 'json')
            self.debug(f"Results downloaded to {output_path}")
            return str(output_path)
        except Exception as e:
            self.debug(f"Error downloading results: {e}")
            return None
    
    def cleanup(self):
        """No cleanup needed for remote instances"""
        self.debug("Remote mode: No cleanup needed")


class CloudZapProvider(ZapInstanceProvider):
    """Provider for cloud-provisioned ZAP instances using Terraform"""
    
    def __init__(self, config, debug_callback=None):
        super().__init__(config, debug_callback)
        self.terraform_manager = None
        self.ssh_executor = None
        self.infrastructure_outputs = None
        self.ssh_key_path = None
        self.ssh_public_key = None
        self.cloud_provider = None
        self.temp_dir = None
    
    def get_mode_name(self):
        return "cloud"
    
    def _generate_ssh_keypair(self):
        """
        Generate ephemeral SSH keypair for cloud instance access
        
        :return: Tuple of (private_key_path, public_key_content)
        """
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
        
        self.debug("Generating SSH keypair...")
        
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Serialize private key
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        # Get public key
        public_key = private_key.public_key()
        public_openssh = public_key.public_bytes(
            encoding=serialization.Encoding.OpenSSH,
            format=serialization.PublicFormat.OpenSSH
        )
        
        # Write private key to temp file
        import tempfile
        self.temp_dir = tempfile.mkdtemp(prefix='kast_zap_')
        private_key_path = os.path.join(self.temp_dir, 'zap_key')
        
        with open(private_key_path, 'wb') as f:
            f.write(private_pem)
        
        # Set correct permissions (SSH requires 600)
        os.chmod(private_key_path, 0o600)
        
        self.debug(f"SSH keypair generated: {private_key_path}")
        return private_key_path, public_openssh.decode('utf-8')
    
    def _prepare_terraform_variables(self, target_url):
        """
        Prepare Terraform variables from configuration
        
        :param target_url: Target URL to scan
        :return: Dictionary of Terraform variables
        """
        cloud_config = self.config.get('cloud', {})
        zap_config = self.config.get('zap_config', {})
        
        # Common variables
        variables = {
            'ssh_public_key': self.ssh_public_key,
            'target_url': target_url,
        }
        
        # Cloud provider specific variables
        if self.cloud_provider == 'aws':
            aws_config = cloud_config.get('aws', {})
            variables.update({
                'region': aws_config.get('region', 'us-east-1'),
                'instance_type': aws_config.get('instance_type', 't3.medium'),
                'zap_docker_image': zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable'),
            })
            # Add AWS credentials if provided in config
            if aws_config.get('access_key_id'):
                variables['aws_access_key_id'] = aws_config['access_key_id']
            if aws_config.get('secret_access_key'):
                variables['aws_secret_access_key'] = aws_config['secret_access_key']
        
        elif self.cloud_provider == 'azure':
            azure_config = cloud_config.get('azure', {})
            variables.update({
                'location': azure_config.get('location', 'eastus'),
                'vm_size': azure_config.get('vm_size', 'Standard_B2s'),
                'zap_docker_image': zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable'),
            })
        
        elif self.cloud_provider == 'gcp':
            gcp_config = cloud_config.get('gcp', {})
            variables.update({
                'project_id': gcp_config.get('project_id'),
                'region': gcp_config.get('region', 'us-central1'),
                'zone': gcp_config.get('zone', 'us-central1-a'),
                'machine_type': gcp_config.get('machine_type', 'e2-medium'),
                'zap_docker_image': zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable'),
            })
        
        # Add tags/labels
        tags = self.config.get('tags', {})
        if tags:
            variables['tags'] = tags
        
        return variables
    
    def provision(self, target_url, output_dir):
        """Provision cloud infrastructure using Terraform"""
        self.debug("Provisioning cloud infrastructure...")
        
        try:
            # Import dependencies
            from kast.scripts.terraform_manager import TerraformManager
            from kast.scripts.ssh_executor import SSHExecutor
            
            cloud_config = self.config.get('cloud', {})
            self.cloud_provider = cloud_config.get('cloud_provider', 'aws')
            
            # Generate SSH keypair
            self.ssh_key_path, self.ssh_public_key = self._generate_ssh_keypair()
            
            # Initialize Terraform Manager
            terraform_dir = Path(__file__).parent.parent / 'terraform' / self.cloud_provider
            workspace_dir = Path(output_dir) / 'terraform_workspace'
            
            self.terraform_manager = TerraformManager(
                str(terraform_dir),
                str(workspace_dir),
                debug_callback=self.debug
            )
            
            # Prepare Terraform variables
            tf_vars = self._prepare_terraform_variables(target_url)
            
            self.debug(f"Using cloud provider: {self.cloud_provider}")
            self.debug("Initializing Terraform...")
            
            # Terraform workflow: init -> plan -> apply
            if not self.terraform_manager.init():
                return False, None, {"error": "Terraform init failed"}
            
            if not self.terraform_manager.plan(tf_vars):
                return False, None, {"error": "Terraform plan failed"}
            
            self.debug("Applying Terraform configuration...")
            if not self.terraform_manager.apply(tf_vars):
                return False, None, {"error": "Terraform apply failed"}
            
            # Get infrastructure outputs
            self.infrastructure_outputs = self.terraform_manager.get_outputs()
            
            if not self.infrastructure_outputs:
                return False, None, {"error": "Failed to get Terraform outputs"}
            
            # Extract connection details
            instance_ip = self.infrastructure_outputs.get('instance_ip', {}).get('value')
            zap_api_url = self.infrastructure_outputs.get('zap_api_url', {}).get('value')
            
            if not instance_ip:
                return False, None, {"error": "No instance IP in Terraform outputs"}
            
            self.debug(f"Infrastructure provisioned - Instance IP: {instance_ip}")
            
            # Wait for SSH to be available
            ssh_config = cloud_config.get('ssh', {})
            ssh_user = ssh_config.get('user', 'ubuntu')
            ssh_timeout = ssh_config.get('connection_timeout', 300)
            
            self.debug("Waiting for SSH to be available...")
            self.ssh_executor = SSHExecutor(
                hostname=instance_ip,
                username=ssh_user,
                key_filename=self.ssh_key_path,
                debug_callback=self.debug
            )
            
            # Try to connect with retries
            max_retries = 30
            retry_interval = 10
            connected = False
            
            for attempt in range(max_retries):
                try:
                    if self.ssh_executor.connect():
                        connected = True
                        self.debug("SSH connection established")
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        self.debug(f"SSH connection attempt {attempt + 1} failed, retrying...")
                        time.sleep(retry_interval)
                    else:
                        self.debug(f"SSH connection failed after {max_retries} attempts: {e}")
            
            if not connected:
                return False, None, {"error": "Failed to establish SSH connection"}
            
            # Deploy ZAP container
            zap_config = self.config.get('zap_config', {})
            docker_image = zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable')
            api_key = zap_config.get('api_key', 'kast-cloud-key')
            
            self.debug("Starting ZAP container on remote instance...")
            
            # Create directories
            self.ssh_executor.execute_command('mkdir -p /home/ubuntu/zap_config')
            self.ssh_executor.execute_command('mkdir -p /home/ubuntu/zap_reports')
            
            # Start ZAP container
            zap_cmd = f"""docker run -d --name zap-scanner \
                -p 8080:8080 \
                -v /home/ubuntu/zap_config:/zap/config \
                -v /home/ubuntu/zap_reports:/zap/reports \
                {docker_image} \
                zap.sh -daemon -port 8080 \
                -config api.key={api_key} \
                -config api.addrs.addr.name=.* \
                -config api.addrs.addr.regex=true"""
            
            result = self.ssh_executor.execute_command(zap_cmd)
            if result['exit_code'] != 0:
                self.debug(f"Failed to start ZAP container: {result['stderr']}")
                return False, None, {"error": "Failed to start ZAP container"}
            
            self.debug("ZAP container started, waiting for API to be ready...")
            
            # Create ZAP API client
            if not zap_api_url:
                zap_api_url = f"http://{instance_ip}:8080"
            
            self.zap_client = ZAPAPIClient(zap_api_url, api_key, debug_callback=self.debug)
            
            # Wait for ZAP to be ready
            if not self.zap_client.wait_for_ready(timeout=180, poll_interval=10):
                return False, None, {"error": "ZAP API not ready"}
            
            self.instance_info = {
                'mode': 'cloud',
                'cloud_provider': self.cloud_provider,
                'instance_ip': instance_ip,
                'zap_api_url': zap_api_url,
                'infrastructure_outputs': self.infrastructure_outputs
            }
            
            return True, self.zap_client, self.instance_info
            
        except Exception as e:
            self.debug(f"Cloud provisioning failed: {e}")
            import traceback
            self.debug(traceback.format_exc())
            return False, None, {"error": str(e)}
    
    def upload_automation_plan(self, plan_content, target_url):
        """Upload automation plan via SSH"""
        if not self.ssh_executor:
            self.debug("No SSH connection available")
            return False
        
        try:
            # Substitute target URL
            plan_content = plan_content.replace('${TARGET_URL}', target_url)
            
            # Write plan to temp file
            temp_plan = os.path.join(self.temp_dir, 'automation_plan.yaml')
            with open(temp_plan, 'w') as f:
                f.write(plan_content)
            
            # Upload via SFTP
            remote_path = '/home/ubuntu/zap_config/automation_plan.yaml'
            self.debug(f"Uploading automation plan to {remote_path}")
            
            if self.ssh_executor.upload_file(temp_plan, remote_path):
                self.debug("Automation plan uploaded successfully")
                
                # Trigger automation via ZAP CLI
                cmd = f"docker exec zap-scanner zap-cli --zap-url http://localhost:8080 open-url {target_url}"
                self.ssh_executor.execute_command(cmd)
                
                return True
            else:
                self.debug("Failed to upload automation plan")
                return False
                
        except Exception as e:
            self.debug(f"Error uploading automation plan: {e}")
            return False
    
    def download_results(self, output_dir, report_name):
        """Download scan results via SSH/SFTP"""
        if not self.ssh_executor:
            self.debug("No SSH connection available")
            return None
        
        try:
            # Remote report path
            remote_path = f'/home/ubuntu/zap_reports/{report_name}'
            
            # Check if file exists
            check_cmd = f"test -f {remote_path} && echo 'exists' || echo 'missing'"
            result = self.ssh_executor.execute_command(check_cmd)
            
            if 'exists' not in result['stdout']:
                self.debug(f"Report not found at {remote_path}, generating via API...")
                # Generate report via API
                local_path = os.path.join(output_dir, report_name)
                self.zap_client.generate_report(local_path, 'json')
                return local_path
            
            # Download via SFTP
            local_path = os.path.join(output_dir, report_name)
            self.debug(f"Downloading report from {remote_path} to {local_path}")
            
            if self.ssh_executor.download_file(remote_path, local_path):
                self.debug("Report downloaded successfully")
                return local_path
            else:
                self.debug("Failed to download report")
                return None
                
        except Exception as e:
            self.debug(f"Error downloading results: {e}")
            return None
    
    def cleanup(self):
        """Teardown cloud infrastructure"""
        self.debug("Cleaning up cloud resources...")
        
        try:
            # Close SSH connection
            if self.ssh_executor:
                try:
                    self.ssh_executor.close()
                    self.debug("SSH connection closed")
                except:
                    pass
            
            # Destroy infrastructure
            if self.terraform_manager:
                self.debug("Running Terraform destroy...")
                if self.terraform_manager.destroy():
                    self.debug("Infrastructure destroyed successfully")
                else:
                    self.debug("Warning: Terraform destroy may have failed")
                
                # Cleanup workspace
                self.terraform_manager.cleanup()
            
            # Remove temp directory with SSH keys
            if self.temp_dir and os.path.exists(self.temp_dir):
                import shutil
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                self.debug("Temporary files cleaned up")
                
        except Exception as e:
            self.debug(f"Error during cleanup: {e}")
