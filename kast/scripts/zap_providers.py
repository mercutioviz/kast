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
            '-config', 'api.addrs.addr.regex=true',
            '-config', 'api.filexfer=true'
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
    
    def __init__(self, config, debug_callback=None):
        super().__init__(config, debug_callback)
        self.plan_id = None  # Store planId for monitoring
    
    def get_mode_name(self):
        return "remote"
    
    def provision(self, target_url, output_dir):
        """Connect to remote ZAP instance"""
        self.debug("Connecting to remote ZAP instance...")
        
        remote_config = self.config.get('remote', {})
        api_url = remote_config.get('api_url')
        api_key = remote_config.get('api_key')
        timeout = remote_config.get('timeout_seconds', 30)
        
        # Check for required configuration
        if not api_url:
            # Check environment variable as fallback
            api_url = os.environ.get('KAST_ZAP_URL')
            if not api_url:
                error_msg = "Remote mode selected but no api_url configured\n"
                error_msg += "Solutions:\n"
                error_msg += "  1. Set environment variable: export KAST_ZAP_URL='http://your-zap:8080'\n"
                error_msg += "  2. Use CLI override: --set zap.remote.api_url=http://your-zap:8080\n"
                error_msg += "  3. Edit config file: remote.api_url in zap_config.yaml"
                self.debug(f"ERROR: {error_msg}")
                return False, None, {"error": error_msg}
        
        # Expand environment variables
        api_url = os.path.expandvars(api_url)
        if api_key:
            api_key = os.path.expandvars(api_key)
        elif not api_key:
            # Check environment variable for API key
            api_key = os.environ.get('KAST_ZAP_API_KEY')
        
        self.debug(f"Connecting to {api_url}")
        
        # Create ZAP API client
        self.zap_client = ZAPAPIClient(api_url, api_key, timeout=timeout, debug_callback=self.debug)
        
        # Test connectivity and get version
        self.debug("Testing ZAP connectivity...")
        success, version, error_msg = self.zap_client.get_version()
        
        if not success:
            self.debug(f"ERROR: Failed to connect to ZAP at {api_url}")
            self.debug(f"ERROR: {error_msg}")
            self.debug(f"Test with: curl {api_url}/JSON/core/view/version/")
            return False, None, {"error": f"ZAP connectivity test failed: {error_msg}"}
        
        # Success - log version
        self.debug(f"✓ Connected to ZAP v{version} at {api_url}")
        
        self.instance_info = {
            'mode': 'remote',
            'api_url': api_url,
            'has_api_key': bool(api_key),
            'zap_version': version
        }
        
        return True, self.zap_client, self.instance_info
    
    def upload_automation_plan(self, plan_content, target_url):
        """
        Upload and execute automation plan via ZAP automation framework API
        
        Uses a two-step process:
        1. Upload the plan file using /OTHER/core/other/fileUpload/
        2. Run the plan using /JSON/automation/action/runPlan/
        
        :param plan_content: YAML content of automation plan
        :param target_url: Target URL to scan
        :return: True if successful
        """
        try:
            # Substitute target URL in the plan
            plan_content = plan_content.replace('${TARGET_URL}', target_url)
            
            self.debug("Uploading automation plan to remote ZAP instance...")
            
            # Step 1: Upload the automation plan file
            from io import BytesIO
            plan_file = BytesIO(plan_content.encode('utf-8'))
            
            # Target filename on ZAP server
            target_filename = 'kast_automation_plan.yaml'
            
            # ZAP expects 'fileContents' as the file parameter
            files = {
                'fileContents': ('automation_plan.yaml', plan_file, 'application/octet-stream')
            }
            
            # Additional data including the target filename
            data = {
                'fileName': target_filename
            }
            
            self.debug("Step 1: Uploading file to ZAP...")
            upload_response = self.zap_client._make_request(
                '/OTHER/core/other/fileUpload/',
                method='POST',
                files=files,
                data=data
            )
            
            if not upload_response:
                self.debug("Failed to upload automation plan file")
                return False
            
            self.debug(f"File upload response: {upload_response}")
            
            # Step 2: Run the uploaded automation plan
            # Extract the full uploaded path from response
            uploaded_path = upload_response.get('Uploaded')
            if not uploaded_path:
                self.debug("Upload response missing 'Uploaded' path")
                return False
            
            self.debug(f"Step 2: Running automation plan at: {uploaded_path}")
            run_response = self.zap_client._make_request(
                '/JSON/automation/action/runPlan/',
                method='POST',
                data={'filePath': uploaded_path}
            )
            
            # Check for planId in response (indicates success)
            if run_response and 'planId' in run_response:
                self.plan_id = run_response.get('planId')
                self.debug(f"✓ Automation plan initiated successfully (planId: {self.plan_id})")
                
                # OPTIONAL: Verify plan is actually running
                try:
                    progress_response = self.zap_client._make_request(
                        '/JSON/automation/view/planProgress/',
                        params={'planId': self.plan_id}
                    )
                    
                    if progress_response and 'started' in progress_response:
                        self.debug(f"✓ Plan confirmed running (started: {progress_response.get('started')})")
                    else:
                        self.debug("Note: Could not verify plan progress (may still be initializing)")
                except Exception as e:
                    self.debug(f"Note: Plan progress check skipped: {e}")
                
                return self.plan_id  # Return planId for monitoring
            else:
                # Check for error response or legacy Result format
                if run_response and run_response.get('Result') == 'OK':
                    self.debug("✓ Automation plan initiated successfully (legacy response)")
                    return True  # Return True for backward compatibility
                
                error = run_response.get('message', 'Unknown error') if run_response else 'No response'
                self.debug(f"Failed to run automation plan: {error}")
                return None  # Return None to indicate failure
                
        except Exception as e:
            self.debug(f"Error uploading automation plan: {e}")
            import traceback
            self.debug(traceback.format_exc())
            return False
    
    def wait_for_plan_completion(self, timeout, poll_interval, output_dir=None):
        """
        Wait for automation plan to complete
        
        :param timeout: Max wait time in seconds
        :param poll_interval: Poll interval in seconds
        :param output_dir: Optional output directory for progress snapshots
        :return: Tuple of (success: bool, progress: dict)
        """
        if not self.plan_id:
            self.debug("No plan ID available for monitoring")
            return False, None
        
        return self.zap_client.wait_for_plan_completion(
            self.plan_id,
            timeout=timeout,
            poll_interval=poll_interval,
            output_dir=output_dir
        )
    
    def download_results(self, output_dir, report_name):
        """Download results via JSON report API"""
        try:
            self.debug("Downloading JSON report from ZAP...")
            report_data = self.zap_client.get_json_report()
            
            output_path = Path(output_dir) / report_name
            import json
            with open(output_path, 'w') as f:
                json.dump(report_data, f, indent=2)
            
            self.debug(f"✓ Report downloaded to {output_path}")
            return str(output_path)
        except Exception as e:
            self.debug(f"Error downloading report: {e}")
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
    
    def _prepare_terraform_variables(self, target_url, use_spot=True):
        """
        Prepare Terraform variables from configuration
        
        Resolution order for each parameter:
        1. CLI override at cloud.{param} (generic, applies to all providers)
        2. CLI override at cloud.{provider}.{param} (provider-specific)
        3. YAML value at cloud.{provider}.{param} (provider-specific)
        4. Hardcoded default

        :param target_url: Target URL to scan
        :param use_spot: Whether to use spot/preemptible instances
        :return: Dictionary of Terraform variables
        """
        zap_config = self.config.get('zap_config', {})
        cloud_config = self.config.get('cloud', {})
        
        self.debug("=== Preparing Terraform Variables ===")
        self.debug(f"Cloud provider: {self.cloud_provider}")
        self.debug(f"Use spot/preemptible: {use_spot}")

        # Common variables
        variables = {
            'ssh_public_key': self.ssh_public_key,
            'target_url': target_url,
        }

        # Cloud provider specific variables
        if self.cloud_provider == 'aws':
            aws_config = cloud_config.get('aws', {})
            
            # Region: CLI generic > CLI aws-specific > YAML aws-specific > default
            region = cloud_config.get('region') or aws_config.get('region', 'us-east-1')
            self.debug(f"AWS region resolution:")
            self.debug(f"  cloud.region (CLI generic): {cloud_config.get('region')}")
            self.debug(f"  cloud.aws.region (YAML): {aws_config.get('region')}")
            self.debug(f"  → Final value: {region}")
            
            # Instance type: CLI generic > CLI aws-specific > YAML aws-specific > default
            instance_type = cloud_config.get('instance_type') or aws_config.get('instance_type', 't3.medium')
            self.debug(f"AWS instance_type resolution:")
            self.debug(f"  cloud.instance_type (CLI): {cloud_config.get('instance_type')}")
            self.debug(f"  cloud.aws.instance_type (YAML): {aws_config.get('instance_type')}")
            self.debug(f"  → Final value: {instance_type}")
            
            # Spot max price
            spot_max_price = cloud_config.get('spot_max_price') or aws_config.get('spot_max_price', '0.05')
            self.debug(f"AWS spot_max_price: {spot_max_price}")
            
            # Allowed CIDRs
            allowed_cidrs = cloud_config.get('allowed_cidrs') or aws_config.get('allowed_cidrs', [])
            if allowed_cidrs:
                self.debug(f"AWS allowed_cidrs: {allowed_cidrs}")
            
            # Auto terminate
            auto_terminate = cloud_config.get('auto_terminate')
            if auto_terminate is None:
                auto_terminate = aws_config.get('auto_terminate', True)
            self.debug(f"AWS auto_terminate: {auto_terminate}")
            
            variables.update({
                'region': region,
                'instance_type': instance_type,
                'use_spot_instance': use_spot,
                'spot_max_price': str(spot_max_price),
                'zap_docker_image': zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable'),
            })
            
            # Optional: AMI ID
            ami_id = aws_config.get('ami_id', '')
            if ami_id:
                variables['ami_id'] = ami_id
                self.debug(f"AWS ami_id: {ami_id}")
            
            # Optional: AWS credentials
            if aws_config.get('access_key_id'):
                variables['aws_access_key_id'] = aws_config['access_key_id']
                self.debug("AWS credentials: access_key_id provided")
            if aws_config.get('secret_access_key'):
                variables['aws_secret_access_key'] = aws_config['secret_access_key']
                self.debug("AWS credentials: secret_access_key provided")
        
        elif self.cloud_provider == 'azure':
            azure_config = cloud_config.get('azure', {})
            
            # Location/region: CLI generic > CLI azure-specific > YAML azure-specific > default
            location = cloud_config.get('region') or azure_config.get('region') or azure_config.get('location', 'eastus')
            self.debug(f"Azure location resolution:")
            self.debug(f"  cloud.region (CLI): {cloud_config.get('region')}")
            self.debug(f"  cloud.azure.region (YAML): {azure_config.get('region')}")
            self.debug(f"  cloud.azure.location (YAML): {azure_config.get('location')}")
            self.debug(f"  → Final value: {location}")
            
            # VM size: CLI generic > CLI azure-specific > YAML azure-specific > default
            vm_size = cloud_config.get('instance_type') or azure_config.get('vm_size', 'Standard_B2s')
            self.debug(f"Azure vm_size: {vm_size}")
            
            # Spot configuration
            spot_enabled = azure_config.get('spot_enabled', True) if use_spot else False
            spot_max_price = cloud_config.get('spot_max_price') or azure_config.get('spot_max_price', -1)
            self.debug(f"Azure spot_enabled: {spot_enabled}, spot_max_price: {spot_max_price}")
            
            variables.update({
                'location': location,
                'vm_size': vm_size,
                'use_spot_instance': use_spot,
                'spot_max_price': spot_max_price,
                'zap_docker_image': zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable'),
            })
            
            # Azure credentials (required)
            for cred_key in ['subscription_id', 'tenant_id', 'client_id', 'client_secret']:
                if azure_config.get(cred_key):
                    variables[f'azure_{cred_key}'] = azure_config[cred_key]
                    self.debug(f"Azure credential: {cred_key} provided")
        
        elif self.cloud_provider == 'gcp':
            gcp_config = cloud_config.get('gcp', {})
            
            # Region: CLI generic > CLI gcp-specific > YAML gcp-specific > default
            region = cloud_config.get('region') or gcp_config.get('region', 'us-central1')
            self.debug(f"GCP region resolution:")
            self.debug(f"  cloud.region (CLI): {cloud_config.get('region')}")
            self.debug(f"  cloud.gcp.region (YAML): {gcp_config.get('region')}")
            self.debug(f"  → Final value: {region}")
            
            # Zone
            zone = gcp_config.get('zone', f'{region}-a')
            self.debug(f"GCP zone: {zone}")
            
            # Machine type: CLI generic > CLI gcp-specific > YAML gcp-specific > default
            machine_type = cloud_config.get('instance_type') or gcp_config.get('machine_type', 'e2-medium')
            self.debug(f"GCP machine_type: {machine_type}")
            
            # Preemptible (GCP's term for spot)
            preemptible = gcp_config.get('preemptible', True) if use_spot else False
            self.debug(f"GCP preemptible: {preemptible}")
            
            variables.update({
                'project_id': gcp_config.get('project_id'),
                'region': region,
                'zone': zone,
                'machine_type': machine_type,
                'use_preemptible_instance': preemptible,
                'zap_docker_image': zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable'),
            })
            
            # GCP credentials
            if gcp_config.get('credentials_file'):
                variables['gcp_credentials_file'] = gcp_config['credentials_file']
                self.debug(f"GCP credentials_file: {gcp_config['credentials_file']}")
        
        # Add tags/labels
        tags = self.config.get('tags', {})
        if tags:
            variables['tags'] = tags
            self.debug(f"Tags: {tags}")
        
        self.debug("=== Terraform Variables Prepared ===")
        # Log final variables (excluding sensitive data)
        safe_vars = {k: v for k, v in variables.items() 
                    if not any(secret in k.lower() for secret in ['key', 'secret', 'password', 'credentials'])}
        self.debug(f"Final variables (non-sensitive): {safe_vars}")
        
        return variables
    
    def _provision_with_retry(self, target_url, output_dir, use_spot=True):
        """
        Provision infrastructure with automatic fallback from spot to on-demand
        
        :param target_url: Target URL to scan
        :param output_dir: Output directory
        :param use_spot: Whether to attempt spot instances first
        :return: Tuple of (success: bool, instance_type: str, error: dict or None)
        """
        # Import dependencies
        from kast.scripts.terraform_manager import TerraformManager
        
        cloud_config = self.config.get('cloud', {})
        self.cloud_provider = cloud_config.get('cloud_provider', 'aws')
        
        # Initialize Terraform Manager
        terraform_dir = Path(__file__).parent.parent / 'terraform' / self.cloud_provider
        workspace_dir = Path(output_dir) / 'terraform_workspace'
        
        self.terraform_manager = TerraformManager(
            self.cloud_provider,
            str(workspace_dir),
            debug_callback=self.debug
        )
        
        # Attempt 1: Try with spot instances (if enabled)
        if use_spot:
            self.debug("=" * 60)
            self.debug("ATTEMPT 1: Provisioning with spot/preemptible instances")
            self.debug("=" * 60)
            
            # Prepare Terraform variables for spot instances
            tf_vars = self._prepare_terraform_variables(target_url, use_spot=True)
            
            self.debug(f"Using cloud provider: {self.cloud_provider}")
            self.terraform_manager.prepare_workspace(str(terraform_dir), tf_vars)
            
            if not self.terraform_manager.init():
                return False, None, {"error": "Terraform init failed"}
            
            if not self.terraform_manager.plan():
                return False, None, {"error": "Terraform plan failed"}
            
            self.debug("Applying Terraform configuration (spot instances)...")
            if self.terraform_manager.apply():
                self.debug("✓ Spot instance provisioned successfully")
                return True, "spot", None
            
            # Check if failure was due to capacity
            if self.terraform_manager.is_capacity_error():
                self.debug("⚠ Spot instance capacity unavailable, will retry with on-demand")
                
                # Clean up failed attempt
                try:
                    self.terraform_manager.destroy(timeout=300)
                    self.terraform_manager.cleanup_workspace()
                except Exception as e:
                    self.debug(f"Note: Cleanup after failed spot attempt: {e}")
            else:
                # Non-capacity error - don't retry
                return False, None, {"error": "Terraform apply failed (non-capacity error)"}
        
        # Attempt 2: Try with on-demand instances
        self.debug("=" * 60)
        self.debug("ATTEMPT 2: Provisioning with on-demand instances")
        self.debug("=" * 60)
        
        # Reinitialize Terraform Manager with new workspace
        workspace_dir = Path(output_dir) / 'terraform_workspace_ondemand'
        self.terraform_manager = TerraformManager(
            self.cloud_provider,
            str(workspace_dir),
            debug_callback=self.debug
        )
        
        # Prepare Terraform variables for on-demand instances
        tf_vars = self._prepare_terraform_variables(target_url, use_spot=False)
        
        self.terraform_manager.prepare_workspace(str(terraform_dir), tf_vars)
        
        if not self.terraform_manager.init():
            return False, None, {"error": "Terraform init failed (on-demand)"}
        
        if not self.terraform_manager.plan():
            return False, None, {"error": "Terraform plan failed (on-demand)"}
        
        self.debug("Applying Terraform configuration (on-demand instances)...")
        if self.terraform_manager.apply():
            self.debug("✓ On-demand instance provisioned successfully")
            return True, "on-demand", None
        else:
            return False, None, {"error": "Terraform apply failed (on-demand)"}
    
    def provision(self, target_url, output_dir):
        """Provision cloud infrastructure using Terraform"""
        self.debug("Provisioning cloud infrastructure...")
        
        try:
            # Import dependencies
            from kast.scripts.ssh_executor import SSHExecutor
            
            cloud_config = self.config.get('cloud', {})
            
            # Generate SSH keypair
            self.ssh_key_path, self.ssh_public_key = self._generate_ssh_keypair()
            
            # Provision with automatic retry/fallback
            success, instance_type, error = self._provision_with_retry(target_url, output_dir)
            
            if not success:
                return False, None, error or {"error": "Infrastructure provisioning failed"}
            
            # Get infrastructure outputs
            self.infrastructure_outputs = self.terraform_manager.get_outputs()
            
            if not self.infrastructure_outputs:
                return False, None, {"error": "Failed to get Terraform outputs"}
            
            # Extract connection details
            instance_ip = self.infrastructure_outputs.get('public_ip')
            zap_api_url = self.infrastructure_outputs.get('zap_api_url')
            
            if not instance_ip:
                return False, None, {"error": "No instance IP in Terraform outputs"}
            
            self.debug(f"Infrastructure provisioned - Instance IP: {instance_ip}")
            
            # Wait for SSH to be available
            ssh_config = cloud_config.get('ssh', {})
            ssh_user = ssh_config.get('user', 'ubuntu')
            ssh_timeout = ssh_config.get('connection_timeout', 300)
            
            self.debug("Waiting for SSH to be available...")
            self.ssh_executor = SSHExecutor(
                host=instance_ip,
                user=ssh_user,
                private_key_path=self.ssh_key_path,
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
            
            # Wait for startup script to complete (it creates /tmp/zap-ready flag)
            self.debug("Waiting for startup script to complete...")
            if not self.ssh_executor.wait_for_file('/tmp/zap-ready', timeout=600, poll_interval=10):
                self.debug("Warning: Startup script completion flag not found, checking Docker directly...")
            
            # Verify Docker is installed and ready
            self.debug("Verifying Docker installation...")
            max_docker_wait = 300  # 5 minutes
            docker_ready = False
            docker_wait_start = time.time()
            
            while time.time() - docker_wait_start < max_docker_wait:
                exit_code, stdout, stderr = self.ssh_executor.execute_command('docker --version')
                if exit_code == 0:
                    self.debug(f"✓ Docker is installed: {stdout.strip()}")
                    docker_ready = True
                    break
                else:
                    elapsed = int(time.time() - docker_wait_start)
                    self.debug(f"Docker not ready yet (waited {elapsed}s), retrying...")
                    time.sleep(10)
            
            if not docker_ready:
                return False, None, {"error": "Docker installation failed or timed out"}
            
            # Deploy ZAP container
            zap_config = self.config.get('zap_config', {})
            docker_image = zap_config.get('docker_image', 'ghcr.io/zaproxy/zaproxy:stable')
            api_key = zap_config.get('api_key', 'kast-cloud-key')
            
            self.debug("Starting ZAP container on remote instance...")
            
            # Create directories
            exit_code, stdout, stderr = self.ssh_executor.execute_command('mkdir -p /home/ubuntu/zap_config')
            exit_code, stdout, stderr = self.ssh_executor.execute_command('mkdir -p /home/ubuntu/zap_reports')
            
            # Start ZAP container
            zap_cmd = f"""docker run -d --name zap-scanner \
                -p 8080:8080 \
                -v /home/ubuntu/zap_config:/zap/config \
                -v /home/ubuntu/zap_reports:/zap/reports \
                {docker_image} \
                zap.sh -daemon -port 8080 \
                -config api.key={api_key} \
                -config api.addrs.addr.name=.* \
                -config api.addrs.addr.regex=true \
                -config api.filexfer=true"""
            
            exit_code, stdout, stderr = self.ssh_executor.execute_command(zap_cmd)
            if exit_code != 0:
                self.debug(f"Failed to start ZAP container: {stderr}")
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
            exit_code, stdout, stderr = self.ssh_executor.execute_command(check_cmd)
            
            if 'exists' not in stdout:
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
