"""
File: plugins/zap_plugin.py
Description: KAST plugin for OWASP ZAP with multi-mode support (local, remote, cloud)
"""

import json
import os
import yaml
from datetime import datetime
from pathlib import Path

from kast.plugins.base import KastPlugin
from kast.scripts.zap_provider_factory import ZapProviderFactory


class ZapPlugin(KastPlugin):
    priority = 200  # Run later (higher number = lower priority)

    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.name = "zap"
        self.display_name = "OWASP ZAP"
        self.description = "OWASP ZAP Active Scanner (Multi-Mode)"
        self.website_url = "https://www.zaproxy.org/"
        self.scan_type = "active"
        self.output_type = "file"
        
        # Provider components
        self.provider = None
        self.zap_client = None
        self.config = None
        self.instance_info = None

    def setup(self, target, output_dir):
        """Setup before run"""
        self.debug("Setup completed.")

    def is_available(self):
        """
        Check if ZAP plugin can run
        
        For multi-mode support, we consider the plugin available if:
        - Docker is installed (for local mode), OR
        - Terraform is installed (for cloud mode)
        - Remote mode is always available if config is provided
        """
        import shutil
        
        # Check for Docker (local mode)
        if shutil.which("docker") is not None:
            return True
        
        # Check for Terraform (cloud mode)
        if shutil.which("terraform") is not None:
            return True
        
        # If neither is available, still return True as remote mode may be configured
        return True

    def _load_config(self):
        """
        Load ZAP configuration from YAML file
        
        Supports both new unified config (zap_config.yaml) and legacy cloud config
        
        :return: Configuration dictionary
        """
        # Try new unified config first
        config_path = Path(__file__).parent.parent / "config" / "zap_config.yaml"
        
        # Fall back to legacy cloud config for backward compatibility
        if not config_path.exists():
            config_path = Path(__file__).parent.parent / "config" / "zap_cloud_config.yaml"
            if config_path.exists():
                self.debug("Using legacy cloud config (consider migrating to zap_config.yaml)")
                # Load and adapt legacy config
                with open(config_path, 'r') as f:
                    legacy_config = yaml.safe_load(f)
                # Convert to new format with cloud mode
                return self._adapt_legacy_config(legacy_config)
        
        if not config_path.exists():
            raise FileNotFoundError(f"ZAP config not found: {config_path}")
        
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # Expand environment variables
        config = self._expand_env_vars(config)
        
        self.debug(f"Loaded ZAP config (mode: {config.get('execution_mode', 'auto')})")
        return config

    def _adapt_legacy_config(self, legacy_config):
        """
        Adapt legacy cloud config to new unified format
        
        :param legacy_config: Legacy cloud configuration
        :return: Adapted configuration
        """
        return {
            'execution_mode': 'cloud',
            'cloud': legacy_config,
            'zap_config': legacy_config.get('zap_config', {}),
            'tags': legacy_config.get('tags', {})
        }

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

    def _load_automation_plan(self):
        """
        Load ZAP automation plan content
        
        :return: YAML content as string
        """
        zap_config = self.config.get('zap_config', {})
        automation_plan_path = Path(zap_config.get('automation_plan', 
                                    'kast/config/zap_automation_plan.yaml'))
        
        if not automation_plan_path.exists():
            # Try relative to this file
            automation_plan_path = Path(__file__).parent.parent / "config" / "zap_automation_plan.yaml"
        
        if not automation_plan_path.exists():
            self.debug("Warning: Automation plan not found, will use API-based scanning")
            return None
        
        with open(automation_plan_path, 'r') as f:
            return f.read()

    def run(self, target, output_dir, report_only):
        """Run ZAP scan using appropriate provider"""
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
            # Load configuration
            self.config = self._load_config()
            
            # Create provider using factory
            factory = ZapProviderFactory(self.config, self.debug)
            self.provider = factory.create_provider()
            
            provider_mode = self.provider.get_mode_name()
            self.debug(f"Using {provider_mode} provider for ZAP scan")
            
            # Provision ZAP instance
            self.debug("Provisioning ZAP instance...")
            success, self.zap_client, self.instance_info = self.provider.provision(target, output_dir)
            
            if not success:
                error_msg = self.instance_info.get('error', 'Unknown error')
                self.debug(f"Failed to provision ZAP instance: {error_msg}")
                return self.get_result_dict("fail", f"Provisioning failed: {error_msg}", timestamp)
            
            self.debug(f"ZAP instance ready: {self.instance_info}")
            
            # Load and upload automation plan (if supported)
            automation_plan = self._load_automation_plan()
            if automation_plan:
                self.debug("Uploading automation plan...")
                if not self.provider.upload_automation_plan(automation_plan, target):
                    self.debug("Warning: Failed to upload automation plan, will use API scanning")
            
            # For remote/local modes without automation framework, use direct API scanning
            use_api_scanning = (provider_mode in ['remote'] or 
                               (provider_mode == 'local' and not automation_plan))
            
            if use_api_scanning:
                self.debug("Using direct API scanning...")
                if not self._run_api_scan(target):
                    self._cleanup_on_failure()
                    return self.get_result_dict("fail", "API scan failed", timestamp)
            
            # Monitor scan progress
            zap_config = self.config.get('zap_config', {})
            timeout_minutes = zap_config.get('timeout_minutes', 60)
            poll_interval = zap_config.get('poll_interval_seconds', 30)
            
            self.debug(f"Monitoring scan (timeout: {timeout_minutes}m, poll: {poll_interval}s)")
            if not self.zap_client.wait_for_scan_completion(
                timeout=timeout_minutes * 60, 
                poll_interval=poll_interval
            ):
                self._cleanup_on_failure()
                return self.get_result_dict("fail", "Scan timeout", timestamp)
            
            # Download results
            self.debug("Downloading scan results...")
            report_name = zap_config.get('report_name', 'zap_report.json')
            local_report = self.provider.download_results(output_dir, report_name)
            
            if not local_report or not os.path.exists(local_report):
                self.debug("Warning: Report not found, generating via API...")
                local_report = os.path.join(output_dir, f"{self.name}.json")
                self.zap_client.generate_report(local_report, 'json')
            
            # Load results
            with open(local_report, 'r') as f:
                results = json.load(f)
            
            # Add provider info to results
            results['provider_mode'] = provider_mode
            results['instance_info'] = self.instance_info
            
            # Cleanup
            self.debug("Cleaning up...")
            self.provider.cleanup()
            
            return self.get_result_dict("success", results, timestamp)
            
        except Exception as e:
            self.debug(f"ZAP plugin failed: {e}")
            import traceback
            self.debug(traceback.format_exc())
            self._cleanup_on_failure()
            return self.get_result_dict("fail", str(e), timestamp)

    def _run_api_scan(self, target):
        """
        Run ZAP scan using direct API calls (for remote/local without automation)
        
        :param target: Target URL
        :return: True if successful
        """
        try:
            # Create a new context
            self.debug(f"Creating ZAP context for {target}")
            
            # Access the target to seed ZAP
            self.zap_client._make_request(f'/JSON/core/action/accessUrl/', 
                                         params={'url': target})
            
            # Start spider scan
            self.debug("Starting spider scan...")
            spider_result = self.zap_client._make_request(
                '/JSON/spider/action/scan/',
                params={'url': target, 'maxChildren': '10'}
            )
            spider_id = spider_result.get('scan', '0')
            self.debug(f"Spider scan started: {spider_id}")
            
            # Start active scan
            self.debug("Starting active scan...")
            ascan_result = self.zap_client._make_request(
                '/JSON/ascan/action/scan/',
                params={'url': target, 'recurse': 'true'}
            )
            ascan_id = ascan_result.get('scan', '0')
            self.debug(f"Active scan started: {ascan_id}")
            
            return True
            
        except Exception as e:
            self.debug(f"API scan failed: {e}")
            return False

    def _cleanup_on_failure(self):
        """Cleanup resources on failure"""
        try:
            if self.provider:
                self.provider.cleanup()
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
        provider_mode = findings.get('provider_mode', 'unknown')
        instance_info = findings.get('instance_info', {})
        
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
            executive_summary = f"ZAP scan completed using {provider_mode} mode. No security issues found."
        else:
            summary = f"Found {total} issues: {risk_counts['High']} High, {risk_counts['Medium']} Medium, {risk_counts['Low']} Low"
            executive_summary = f"ZAP scan ({provider_mode} mode) identified {total} security findings requiring attention."
        
        # Build details
        details = f"Execution Mode: {provider_mode}\n"
        details += f"Total Alerts: {total}\n"
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
            "provider_mode": provider_mode,
            "instance_info": instance_info
        }
        
        processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
        with open(processed_path, "w") as f:
            json.dump(processed, f, indent=2)
        
        return processed_path
