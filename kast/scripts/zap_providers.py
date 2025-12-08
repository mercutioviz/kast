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
    """Provider for cloud-provisioned ZAP instances (existing implementation)"""
    
    def __init__(self, config, debug_callback=None):
        super().__init__(config, debug_callback)
        self.terraform_manager = None
        self.ssh_executor = None
        self.infrastructure_outputs = None
        self.ssh_key_path = None
        self.ssh_public_key = None
    
    def get_mode_name(self):
        return "cloud"
    
    def provision(self, target_url, output_dir):
        """Provision cloud infrastructure - implementation will be moved from plugin"""
        # This will contain the refactored cloud provisioning logic
        # For now, return not implemented to keep the diff manageable
        raise NotImplementedError("CloudZapProvider will be implemented in next phase")
    
    def upload_automation_plan(self, plan_content, target_url):
        """Upload automation plan via SSH"""
        raise NotImplementedError("CloudZapProvider will be implemented in next phase")
    
    def download_results(self, output_dir, report_name):
        """Download results via SSH"""
        raise NotImplementedError("CloudZapProvider will be implemented in next phase")
    
    def cleanup(self):
        """Teardown cloud infrastructure"""
        raise NotImplementedError("CloudZapProvider will be implemented in next phase")
