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
                        "default": True,
                        "description": "Use ZAP automation framework with YAML config (default for all modes)"
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
                    },
                    "use_automation_framework": {
                        "type": "boolean",
                        "default": True,
                        "description": "Use ZAP automation framework with YAML config (default for all modes)"
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
        
        Search order (consistent with ConfigManager):
        1. ./kast_config.yaml (project) - plugins.zap section
        2. ~/.config/kast/config.yaml (user) - plugins.zap section
        3. /etc/kast/config.yaml (system) - plugins.zap section
        4. kast/config/zap_config.yaml (installation - backward compat)
        5. kast/config/zap_cloud_config.yaml (legacy - backward compat)
        
        :return: Configuration dictionary
        """
        # DEBUG: Check if ConfigManager is available
        if self.config_manager:
            self.debug(f"ConfigManager available: {type(self.config_manager)}")
        else:
            self.debug("WARNING: ConfigManager is None - CLI overrides will not be applied!")
        
        # Define search paths (same as ConfigManager)
        unified_config_paths = [
            Path("./kast_config.yaml"),  # Project-specific
            Path.home() / ".config" / "kast" / "config.yaml",  # User config (XDG)
            Path("/etc/kast/config.yaml"),  # System-wide
        ]
        
        config = None
        config_source = None
        
        # First, try unified config files (look for plugins.zap section)
        for config_path in unified_config_paths:
            config_path = config_path.expanduser()
            if config_path.exists():
                try:
                    self.debug(f"Checking for ZAP config in {config_path}")
                    with open(config_path, 'r') as f:
                        unified_config = yaml.safe_load(f)
                    
                    # Check if this file has a plugins.zap section
                    if isinstance(unified_config, dict) and \
                       'plugins' in unified_config and \
                       'zap' in unified_config['plugins']:
                        config = unified_config['plugins']['zap']
                        config_source = str(config_path)
                        self.debug(f"Found ZAP config in unified format: {config_path}")
                        break
                except Exception as e:
                    self.debug(f"Error reading {config_path}: {e}")
                    continue
        
        # If not found in unified configs, try standalone ZAP config files
        if config is None:
            standalone_paths = [
                Path(__file__).parent.parent / "config" / "zap_config.yaml",
                Path(__file__).parent.parent / "config" / "zap_cloud_config.yaml"
            ]
            
            for config_path in standalone_paths:
                if config_path.exists():
                    try:
                        self.debug(f"Checking standalone ZAP config: {config_path}")
                        with open(config_path, 'r') as f:
                            standalone_config = yaml.safe_load(f)
                        
                        # Check if this is legacy cloud config format
                        if 'cloud_provider' in standalone_config and 'execution_mode' not in standalone_config:
                            self.debug("Using legacy cloud config format")
                            config = self._adapt_legacy_config(standalone_config)
                        else:
                            config = standalone_config
                        
                        config_source = str(config_path)
                        self.debug(f"Found ZAP config in standalone format: {config_path}")
                        break
                    except Exception as e:
                        self.debug(f"Error reading {config_path}: {e}")
                        continue
        
        # If still no config found, raise error
        if config is None:
            searched_paths = [str(p) for p in unified_config_paths] + \
                           [str(p) for p in standalone_paths]
            raise FileNotFoundError(
                f"ZAP config not found. Searched:\n" + 
                "\n".join(f"  - {p}" for p in searched_paths)
            )
        
        # Expand environment variables
        config = self._expand_env_vars(config)
        
        # Apply CLI overrides from ConfigManager
        if self.config_manager:
            config = self._apply_cli_overrides(config)
        
        self.debug(f"Loaded ZAP config from {config_source} (mode: {config.get('execution_mode', 'auto')})")
        return config
    
    def _apply_cli_overrides(self, config):
        """
        Apply CLI overrides from ConfigManager to loaded YAML config
        
        Only overrides strategic parameters that users commonly adjust.
        Preserves the hierarchical YAML structure.
        
        :param config: Configuration dictionary from YAML
        :return: Configuration with CLI overrides applied
        """
        self.debug("=== Applying CLI Overrides ===")
        self.debug(f"Config before overrides - execution_mode: {config.get('execution_mode', 'NOT SET')}")
        
        if not self.config_manager:
            self.debug("No ConfigManager available, skipping CLI overrides")
            return config
        
        # Get entire plugin config from ConfigManager (includes CLI overrides)
        try:
            plugin_config = self.config_manager.get_plugin_config(self.name)
            self.debug(f"Retrieved plugin config from ConfigManager: {list(plugin_config.keys())}")
        except Exception as e:
            self.debug(f"Error getting plugin config from ConfigManager: {e}")
            return config
        
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
            'local.use_automation_framework',
            'remote.api_url',
            'remote.api_key',
            'remote.timeout_seconds',
            'remote.verify_ssl',
            'remote.use_automation_framework',
            'cloud.cloud_provider',
            'cloud.use_automation_framework',
            'zap_config.timeout_minutes',
            'zap_config.poll_interval_seconds',
            'zap_config.report_name',
            'zap_config.automation_plan'
        ]
        
        override_count = 0
        for param_path in overrideable_params:
            # Extract value from plugin config using nested path
            self.debug(f"  Checking override for: {param_path}")
            override_value = self._get_nested_value(plugin_config, param_path)
            self.debug(f"    Found in plugin_config: {override_value} (type: {type(override_value).__name__ if override_value is not None else 'None'})")
            
            # Only apply if value differs from what's in YAML config
            yaml_value = self._get_nested_value(config, param_path)
            
            if override_value is not None and override_value != yaml_value:
                # Apply the override to nested config
                self._set_nested_value(config, param_path, override_value)
                self.debug(f"✓ CLI override applied: {param_path} = {override_value} (was: {yaml_value})")
                override_count += 1
        
        self.debug(f"=== Applied {override_count} CLI override(s) ===")
        self.debug(f"Config after overrides - execution_mode: {config.get('execution_mode', 'NOT SET')}")
        
        return config
    
    def _get_nested_value(self, config, path):
        """
        Get a value from nested dictionary using dot notation path
        
        Example: _get_nested_value(config, 'local.api_port')
                 returns config['local']['api_port']
        
        :param config: Configuration dictionary
        :param path: Dot-notation path (e.g., 'local.api_port')
        :return: Value at path, or None if not found
        """
        keys = path.split('.')
        current = config
        
        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        
        return current
    
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

    def _validate_automation_plan(self, plan_content):
        """
        Validate ZAP automation plan YAML
        
        :param plan_content: YAML content as string
        :return: Tuple of (is_valid: bool, error_message: str or None)
        """
        try:
            # Parse YAML
            plan = yaml.safe_load(plan_content)
            
            # Basic structure validation
            if not isinstance(plan, dict):
                return False, "Automation plan must be a YAML dictionary"
            
            # Check for required top-level keys
            if 'env' not in plan:
                return False, "Automation plan missing required 'env' section"
            
            if 'jobs' not in plan:
                return False, "Automation plan missing required 'jobs' section"
            
            # Validate env section
            env = plan.get('env', {})
            if not isinstance(env, dict):
                return False, "'env' section must be a dictionary"
            
            # Validate jobs section
            jobs = plan.get('jobs', [])
            if not isinstance(jobs, list):
                return False, "'jobs' section must be a list"
            
            if len(jobs) == 0:
                return False, "'jobs' section cannot be empty"
            
            # Validate each job has a type
            for idx, job in enumerate(jobs):
                if not isinstance(job, dict):
                    return False, f"Job at index {idx} must be a dictionary"
                if 'type' not in job:
                    return False, f"Job at index {idx} missing required 'type' field"
            
            self.debug("Automation plan validation passed")
            return True, None
            
        except yaml.YAMLError as e:
            return False, f"YAML parsing error: {str(e)}"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    def _load_automation_plan(self):
        """
        Load and validate ZAP automation plan content
        
        :return: YAML content as string, or None if not found/invalid
        """
        zap_config = self.config.get('zap_config', {})
        automation_plan_path = Path(zap_config.get('automation_plan', 
                                    'kast/config/zap_automation_plan.yaml'))
        
        if not automation_plan_path.exists():
            # Try relative to this file
            automation_plan_path = Path(__file__).parent.parent / "config" / "zap_automation_plan.yaml"
        
        if not automation_plan_path.exists():
            self.debug("Warning: Automation plan not found")
            return None
        
        try:
            with open(automation_plan_path, 'r') as f:
                plan_content = f.read()
            
            # Validate the plan
            is_valid, error_msg = self._validate_automation_plan(plan_content)
            if not is_valid:
                self.debug(f"Automation plan validation failed: {error_msg}")
                return None
            
            self.debug(f"Loaded automation plan from {automation_plan_path}")
            return plan_content
            
        except Exception as e:
            self.debug(f"Error loading automation plan: {e}")
            return None

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
            
            # Validate remote mode requirements
            execution_mode = self.config.get('execution_mode', 'auto')
            if execution_mode == 'remote':
                remote_config = self.config.get('remote', {})
                api_url = remote_config.get('api_url', '')
                api_key = remote_config.get('api_key', '')
                
                # Check if URL is missing or unexpanded environment variable
                if not api_url or api_url.startswith('${'):
                    error_msg = "\n" + "="*70 + "\n"
                    error_msg += "ERROR: Remote ZAP mode requires a ZAP instance URL.\n"
                    error_msg += "="*70 + "\n\n"
                    error_msg += "Provide the URL using one of these methods:\n\n"
                    error_msg += "  1. CLI argument:\n"
                    error_msg += "     --set zap.remote.api_url=http://zap.example.com:8080\n\n"
                    error_msg += "  2. Environment variable:\n"
                    error_msg += "     export KAST_ZAP_URL=http://zap.example.com:8080\n\n"
                    error_msg += "  3. Config file (zap_config.yaml):\n"
                    error_msg += "     remote:\n"
                    error_msg += "       api_url: http://zap.example.com:8080\n\n"
                    
                    # Also check and warn about missing API key (in yellow)
                    if not api_key or api_key.startswith('${'):
                        error_msg += "\033[93m"  # Yellow color
                        error_msg += "WARNING: No ZAP API key provided.\n"
                        error_msg += "If your ZAP instance requires authentication, provide:\n\n"
                        error_msg += "  1. CLI: --set zap.remote.api_key=YOUR_KEY\n"
                        error_msg += "  2. Environment: export KAST_ZAP_API_KEY=YOUR_KEY\n"
                        error_msg += "  3. Config file: Set remote.api_key in zap_config.yaml\n"
                        error_msg += "\033[0m\n"  # Reset color
                    
                    error_msg += "="*70 + "\n"
                    
                    # Print to console (not just debug log)
                    print(error_msg)
                    self.debug("Remote mode validation failed: Missing api_url")
                    return self.get_result_dict("fail", "Remote mode requires api_url to be configured", timestamp)
                
                # Warn about missing API key (but don't fail) - in yellow
                if not api_key or api_key.startswith('${'):
                    warning_msg = "\n\033[93m"  # Yellow color
                    warning_msg += "="*70 + "\n"
                    warning_msg += "WARNING: No ZAP API key provided for remote mode.\n"
                    warning_msg += "="*70 + "\n\n"
                    warning_msg += "If your ZAP instance requires authentication, provide the key using:\n\n"
                    warning_msg += "  1. CLI: --set zap.remote.api_key=YOUR_KEY\n"
                    warning_msg += "  2. Environment: export KAST_ZAP_API_KEY=YOUR_KEY\n"
                    warning_msg += "  3. Config file: Set remote.api_key in zap_config.yaml\n\n"
                    warning_msg += "Proceeding without API key (works if ZAP has API key disabled)...\n"
                    warning_msg += "="*70 + "\n"
                    warning_msg += "\033[0m"  # Reset color
                    print(warning_msg)
                    self.debug("Remote mode: No API key provided")
            
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
            
            # Determine if using automation framework based on mode config
            mode_config = self.config.get(provider_mode, {})
            use_automation = mode_config.get('use_automation_framework', True)
            
            if use_automation:
                # Load and validate automation plan
                automation_plan = self._load_automation_plan()
                
                if not automation_plan:
                    # Automation framework enabled but plan is missing/invalid - FAIL
                    error_msg = "Automation framework enabled but automation plan is missing or invalid"
                    self.debug(f"ERROR: {error_msg}")
                    self._cleanup_on_failure()
                    return self.get_result_dict("fail", error_msg, timestamp)
                
                # Upload and execute automation plan
                self.debug("Uploading and executing automation plan...")
                if not self.provider.upload_automation_plan(automation_plan, target):
                    # Upload failed - FAIL (per requirement: failed AF attempts should fail the scan)
                    error_msg = "Failed to upload/execute automation plan"
                    self.debug(f"ERROR: {error_msg}")
                    self._cleanup_on_failure()
                    return self.get_result_dict("fail", error_msg, timestamp)
                
                self.debug("Automation framework initiated successfully")
            else:
                # Automation framework explicitly disabled - use direct API
                self.debug("Automation framework disabled, using direct API scanning...")
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
        # Load findings - handle multiple input types
        findings = {}
        
        if isinstance(raw_output, str):
            # Could be a file path or error message
            if os.path.isfile(raw_output):
                with open(raw_output, "r") as f:
                    findings = json.load(f)
            else:
                # It's an error message string
                self.debug(f"Post-process received error string: {raw_output}")
                findings = {'error': raw_output}
        elif isinstance(raw_output, dict):
            # Could be results dict or get_result_dict structure
            if 'results' in raw_output:
                findings = raw_output['results']
                # Handle case where results is a string (error case)
                if isinstance(findings, str):
                    findings = {'error': findings}
            else:
                findings = raw_output
        
        # Parse ZAP alerts (if available)
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
