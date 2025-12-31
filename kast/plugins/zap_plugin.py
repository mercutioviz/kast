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
    
    # Configuration schema for kast-web integration
    # Note: ZAP uses hierarchical YAML config, schema mirrors that structure
    config_schema = {
        "type": "object",
        "title": "OWASP ZAP Configuration",
        "description": "Multi-mode configuration for OWASP ZAP security scanner (local/remote/cloud)",
        "properties": {
            "execution_mode": {
                "type": "string",
                "enum": ["auto", "local", "remote", "cloud"],
                "default": "auto",
                "description": "Execution mode: auto (intelligent discovery), local (Docker), remote (existing instance), cloud (ephemeral infrastructure)"
            },
            "auto_discovery": {
                "type": "object",
                "title": "Auto-Discovery Settings",
                "properties": {
                    "prefer_local": {
                        "type": "boolean",
                        "default": True,
                        "description": "Prefer local Docker over cloud when auto-discovering"
                    },
                    "check_env_vars": {
                        "type": "boolean",
                        "default": True,
                        "description": "Check for KAST_ZAP_URL and KAST_ZAP_API_KEY environment variables"
                    }
                }
            },
            "local": {
                "type": "object",
                "title": "Local Docker Configuration",
                "properties": {
                    "docker_image": {
                        "type": "string",
                        "default": "ghcr.io/zaproxy/zaproxy:stable",
                        "description": "Docker image for local ZAP container"
                    },
                    "auto_start": {
                        "type": "boolean",
                        "default": True,
                        "description": "Automatically start ZAP container if not running"
                    },
                    "api_port": {
                        "type": "integer",
                        "default": 8080,
                        "minimum": 1024,
                        "maximum": 65535,
                        "description": "API port for local ZAP instance"
                    },
                    "api_key": {
                        "type": "string",
                        "default": "kast-local",
                        "description": "API key for local ZAP authentication"
                    },
                    "container_name": {
                        "type": "string",
                        "default": "kast-zap-local",
                        "description": "Docker container name"
                    },
                    "cleanup_on_completion": {
                        "type": "boolean",
                        "default": False,
                        "description": "Remove container after scan (False = keep for reuse)"
                    },
                    "use_automation_framework": {
                        "type": "boolean",
                        "default": True,
                        "description": "Use ZAP automation framework vs direct API"
                    }
                }
            },
            "remote": {
                "type": "object",
                "title": "Remote ZAP Configuration",
                "properties": {
                    "api_url": {
                        "type": "string",
                        "default": "",
                        "description": "Remote ZAP API URL (supports env vars: ${KAST_ZAP_URL})"
                    },
                    "api_key": {
                        "type": "string",
                        "default": "",
                        "description": "Remote ZAP API key (supports env vars: ${KAST_ZAP_API_KEY})"
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 5,
                        "maximum": 300,
                        "description": "Connection timeout in seconds"
                    },
                    "verify_ssl": {
                        "type": "boolean",
                        "default": True,
                        "description": "Verify SSL certificates"
                    },
                    "use_automation_framework": {
                        "type": "boolean",
                        "default": False,
                        "description": "Use automation framework (remote typically uses direct API)"
                    }
                }
            },
            "cloud": {
                "type": "object",
                "title": "Cloud Provider Configuration",
                "properties": {
                    "cloud_provider": {
                        "type": "string",
                        "enum": ["aws", "azure", "gcp"],
                        "default": "aws",
                        "description": "Cloud provider for ephemeral infrastructure"
                    }
                    # Note: Full cloud config remains in YAML file due to complexity
                    # (AWS/Azure/GCP specific settings, credentials, Terraform state)
                }
            },
            "zap_config": {
                "type": "object",
                "title": "Common ZAP Settings",
                "properties": {
                    "timeout_minutes": {
                        "type": "integer",
                        "default": 60,
                        "minimum": 5,
                        "maximum": 720,
                        "description": "Maximum scan duration in minutes"
                    },
                    "poll_interval_seconds": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 5,
                        "maximum": 300,
                        "description": "Status polling interval in seconds"
                    },
                    "report_name": {
                        "type": "string",
                        "default": "zap_report.json",
                        "description": "Output report filename"
                    },
                    "automation_plan": {
                        "type": "string",
                        "default": "kast/config/zap_automation_plan.yaml",
                        "description": "Path to ZAP automation plan YAML file"
                    }
                }
            }
        }
    }

    def __init__(self, cli_args, config_manager=None):
        # IMPORTANT: Set plugin name BEFORE calling super().__init__()
        # so that schema registration uses the correct plugin name
        self.name = "zap"
        self.display_name = "OWASP ZAP"
        self.description = "OWASP ZAP Active Scanner (Multi-Mode)"
        self.website_url = "https://www.zaproxy.org/"
        self.scan_type = "active"
        self.output_type = "file"
        
        # Now call parent init (this will register our schema under correct name)
        super().__init__(cli_args, config_manager)
        
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
        Load ZAP configuration from YAML file with ConfigManager CLI overrides
        
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
                config = self._adapt_legacy_config(legacy_config)
            else:
                raise FileNotFoundError(f"ZAP config not found: {config_path}")
        else:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
        
        # Expand environment variables
        config = self._expand_env_vars(config)
        
        # Apply CLI overrides from ConfigManager
        if self.config_manager:
            config = self._apply_cli_overrides(config)
        
        self.debug(f"Loaded ZAP config (mode: {config.get('execution_mode', 'auto')})")
        return config
    
    def _apply_cli_overrides(self, config):
        """
        Apply CLI overrides from ConfigManager to loaded YAML config
        
        Only overrides strategic parameters that users commonly adjust.
        Preserves the hierarchical YAML structure.
        
        :param config: Configuration dictionary from YAML
        :return: Configuration with CLI overrides applied
        """
        # Strategic parameters that can be overridden via CLI
        # Format: 'nested.key.path' maps to config['nested']['key']['path']
        overrideable_params = [
            'execution_mode',
            'auto_discovery.prefer_local',
            'auto_discovery.check_env_vars',
            'local.docker_image',
            'local.auto_start',
            'local.api_port',
            'local.container_name',
            'local.cleanup_on_completion',
            'remote.api_url',
            'remote.api_key',
            'remote.timeout_seconds',
            'remote.verify_ssl',
            'cloud.cloud_provider',
            'zap_config.timeout_minutes',
            'zap_config.poll_interval_seconds',
            'zap_config.report_name'
        ]
        
        for param_path in overrideable_params:
            # Get value directly from ConfigManager (avoid circular dependency with self.config)
            override_value = None
            if self.config_manager:
                try:
                    override_value = self.config_manager.get_config(self.name, param_path)
                except:
                    pass
            
            if override_value is not None:
                # Apply the override to nested config
                self._set_nested_value(config, param_path, override_value)
                self.debug(f"CLI override applied: {param_path} = {override_value}")
        
        return config
    
    def _set_nested_value(self, config, path, value):
        """
        Set a value in nested dictionary using dot notation path
        
        Example: _set_nested_value(config, 'local.api_port', 8081)
                 sets config['local']['api_port'] = 8081
        
        :param config: Configuration dictionary
        :param path: Dot-notation path (e.g., 'local.api_port')
        :param value: Value to set
        """
        keys = path.split('.')
        current = config
        
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        # Set the final value
        current[keys[-1]] = value

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
        
        # Calculate findings_count - total number of security alerts/vulnerabilities
        findings_count = total = sum(risk_counts.values())
        
        # Build summary
        if total == 0:
            summary = "No vulnerabilities detected"
            executive_summary = f"ZAP scan completed using {provider_mode} mode. No security issues found."
        else:
            summary = f"Found {total} issues: {risk_counts['High']} High, {risk_counts['Medium']} Medium, {risk_counts['Low']} Low"
            executive_summary = f"ZAP scan ({provider_mode} mode) identified {total} security findings requiring attention."
        
        self.debug(f"{self.name} findings_count: {findings_count}")
        
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
            "findings_count": findings_count,
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
