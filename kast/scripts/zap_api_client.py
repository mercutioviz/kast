"""
ZAP API Client for Cloud Plugin
Handles interaction with OWASP ZAP REST API
"""

import requests
import time
import json
from pathlib import Path


class ZAPAPIClient:
    """Client for interacting with OWASP ZAP REST API"""
    
    def __init__(self, api_url, api_key=None, timeout=30, debug_callback=None):
        """
        Initialize ZAP API client
        
        :param api_url: Base URL for ZAP API (e.g., http://host:8080)
        :param api_key: Optional API key for authentication
        :param timeout: Request timeout in seconds
        :param debug_callback: Optional callback function for debug messages
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        self.debug = debug_callback or (lambda x: None)
        self.session = requests.Session()
        
        # Add API key to all requests if provided
        if self.api_key:
            self.session.params = {'apikey': self.api_key}
    
    def _make_request(self, endpoint, method='GET', params=None, data=None, files=None):
        """
        Make HTTP request to ZAP API
        
        :param endpoint: API endpoint path
        :param method: HTTP method (GET, POST, etc.)
        :param params: Query parameters
        :param data: Request body data
        :param files: Files to upload
        :return: Response JSON or None
        """
        url = f"{self.api_url}{endpoint}"
        
        try:
            self.debug(f"ZAP API request: {method} {url}")
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                data=data,
                files=files,
                timeout=self.timeout
            )
            
            response.raise_for_status()
            
            # Try to parse JSON response
            try:
                result = response.json()
                self.debug(f"ZAP API response: {str(result)[:200]}")
                return result
            except json.JSONDecodeError:
                self.debug(f"Non-JSON response: {response.text[:200]}")
                return {'text': response.text}
                
        except requests.exceptions.RequestException as e:
            self.debug(f"ZAP API request failed: {e}")
            raise
    
    def check_connection(self):
        """
        Check if ZAP is accessible
        
        :return: True if accessible, False otherwise
        """
        try:
            result = self._make_request('/JSON/core/view/version/')
            self.debug(f"ZAP version: {result.get('version', 'unknown')}")
            return True
        except Exception as e:
            self.debug(f"Connection check failed: {e}")
            return False
    
    def get_version(self):
        """
        Get ZAP version information with detailed error reporting
        
        :return: Tuple of (success: bool, version: str, error_msg: str)
        """
        try:
            result = self._make_request('/JSON/core/view/version/')
            if result and 'version' in result:
                version = result.get('version', 'unknown')
                return True, version, None
            else:
                return False, None, "Invalid response from ZAP (no version field)"
        except requests.exceptions.ConnectionError as e:
            return False, None, f"Connection refused - verify ZAP is running and accessible at {self.api_url}"
        except requests.exceptions.Timeout:
            return False, None, f"Connection timeout - ZAP at {self.api_url} is not responding"
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                return False, None, "Authentication failed - check API key"
            elif e.response.status_code == 403:
                return False, None, "Access forbidden - verify API key permissions"
            else:
                return False, None, f"HTTP {e.response.status_code}: {e.response.reason}"
        except Exception as e:
            return False, None, f"Unexpected error: {str(e)}"
    
    def wait_for_ready(self, timeout=300, poll_interval=10):
        """
        Wait for ZAP to be ready
        
        :param timeout: Maximum wait time in seconds
        :param poll_interval: Seconds between checks
        :return: True if ready, False if timeout
        """
        self.debug(f"Waiting for ZAP to be ready (timeout: {timeout}s)")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.check_connection():
                self.debug("ZAP is ready")
                return True
            time.sleep(poll_interval)
        
        self.debug("Timeout waiting for ZAP")
        return False
    
    def upload_automation_plan(self, plan_path, remote_plan_path='/zap/config/automation_plan.yaml'):
        """
        Upload automation framework plan to ZAP
        Note: This requires SSH access, not API. This is a placeholder.
        
        :param plan_path: Local path to automation plan
        :param remote_plan_path: Remote path where plan will be uploaded
        :return: Remote path
        """
        # This method is informational - actual upload happens via SSH
        self.debug(f"Automation plan will be uploaded to: {remote_plan_path}")
        return remote_plan_path
    
    def start_automation_scan(self, plan_path, target_url):
        """
        Start ZAP automation framework scan
        Note: This typically requires running ZAP with the -autorun flag
        
        :param plan_path: Path to automation plan YAML
        :param target_url: Target URL to scan
        :return: Scan information
        """
        # The automation framework is typically started via command line, not API
        # This method documents the expected behavior
        self.debug(f"Starting automation scan for {target_url}")
        
        return {
            'plan_path': plan_path,
            'target_url': target_url,
            'status': 'started'
        }
    
    def get_scan_status(self):
        """
        Get current scan status
        
        :return: Status information
        """
        try:
            # Get spider status
            spider_status = self._make_request('/JSON/spider/view/status/')
            
            # Get active scan status
            active_scan_status = self._make_request('/JSON/ascan/view/status/')
            
            # Get number of alerts
            alerts = self._make_request('/JSON/core/view/numberOfAlerts/')
            
            status = {
                'spider_status': spider_status.get('status', '0'),
                'active_scan_status': active_scan_status.get('status', '0'),
                'alert_count': alerts.get('numberOfAlerts', '0'),
                'in_progress': self._is_scan_in_progress(spider_status, active_scan_status)
            }
            
            self.debug(f"Scan status: {status}")
            return status
            
        except Exception as e:
            self.debug(f"Failed to get scan status: {e}")
            return None
    
    def _is_scan_in_progress(self, spider_status, active_scan_status):
        """
        Determine if any scan is in progress
        
        :param spider_status: Spider status dict
        :param active_scan_status: Active scan status dict
        :return: True if scan in progress
        """
        try:
            spider_pct = int(spider_status.get('status', '100'))
            ascan_pct = int(active_scan_status.get('status', '100'))
            
            return spider_pct < 100 or ascan_pct < 100
        except:
            return False
    
    def wait_for_scan_completion(self, timeout=3600, poll_interval=30):
        """
        Poll scan status until completion or timeout
        
        :param timeout: Maximum wait time in seconds
        :param poll_interval: Seconds between status checks
        :return: True if completed, False if timeout
        """
        self.debug(f"Waiting for scan completion (timeout: {timeout}s, poll: {poll_interval}s)")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self.get_scan_status()
            
            if status and not status.get('in_progress', True):
                self.debug("Scan completed")
                return True
            
            elapsed = int(time.time() - start_time)
            self.debug(f"Scan still in progress... ({elapsed}s elapsed)")
            
            time.sleep(poll_interval)
        
        self.debug("Timeout waiting for scan completion")
        return False
    
    def get_alerts(self, base_url=None):
        """
        Retrieve all alerts from ZAP
        
        :param base_url: Optional filter by base URL
        :return: List of alerts
        """
        try:
            params = {}
            if base_url:
                params['baseurl'] = base_url
            
            result = self._make_request('/JSON/core/view/alerts/', params=params)
            alerts = result.get('alerts', [])
            
            self.debug(f"Retrieved {len(alerts)} alerts")
            return alerts
            
        except Exception as e:
            self.debug(f"Failed to retrieve alerts: {e}")
            return []
    
    def generate_report(self, output_path, report_type='json', title='KAST ZAP Scan'):
        """
        Generate scan report
        
        :param output_path: Path to save report
        :param report_type: Report format (json, html, xml)
        :param title: Report title
        :return: Path to generated report
        """
        try:
            self.debug(f"Generating {report_type} report")
            
            if report_type == 'json':
                # Get all alerts
                alerts = self.get_alerts()
                
                # Build report structure
                report = {
                    'title': title,
                    'alerts': alerts,
                    'alert_count': len(alerts)
                }
                
                # Save to file
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, 'w') as f:
                    json.dump(report, f, indent=2)
                
                self.debug(f"Report saved to {output_path}")
                return str(output_path)
                
            else:
                # For HTML/XML reports, use ZAP's report generation
                endpoint = f'/OTHER/core/other/{report_type}report/'
                response = self._make_request(endpoint)
                
                output_path = Path(output_path)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_path, 'w') as f:
                    f.write(response.get('text', ''))
                
                return str(output_path)
                
        except Exception as e:
            self.debug(f"Failed to generate report: {e}")
            raise
    
    def shutdown_zap(self):
        """
        Shutdown ZAP instance
        
        :return: True if successful
        """
        try:
            self.debug("Shutting down ZAP")
            self._make_request('/JSON/core/action/shutdown/')
            return True
        except Exception as e:
            self.debug(f"Failed to shutdown ZAP: {e}")
            return False
    
    def get_zap_info(self):
        """
        Get ZAP version and configuration information
        
        :return: Dictionary with ZAP info
        """
        try:
            version = self._make_request('/JSON/core/view/version/')
            alerts_summary = self._make_request('/JSON/core/view/alertsSummary/')
            
            return {
                'version': version.get('version', 'unknown'),
                'alerts_summary': alerts_summary
            }
        except Exception as e:
            self.debug(f"Failed to get ZAP info: {e}")
            return {}
