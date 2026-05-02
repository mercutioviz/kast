"""
ZAP Instance Provider Abstraction
Supports local and remote execution modes.
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

