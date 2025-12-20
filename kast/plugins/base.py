"""
File: plugins/base.py
Description: Base class for all KAST plugins. Provides required interface and properties.
"""

from abc import ABC, abstractmethod
from datetime import datetime
import shutil

class KastPlugin(ABC):
    """
    Abstract base class for all KAST plugins.
    """
    priority = 100  # Default priority (lower number = higher priority)
    
    # Plugin configuration schema (override in subclasses)
    config_schema = {
        "type": "object",
        "title": "Base Plugin Configuration",
        "description": "Base configuration schema for KAST plugins",
        "properties": {}
    }

    def __init__(self, cli_args, config_manager=None):
        """
        Initialize the plugin with CLI arguments and optional config manager.
        :param cli_args: Namespace object from argparse containing CLI arguments.
        :param config_manager: ConfigManager instance for loading plugin configuration.
        """
        self.cli_args = cli_args
        self.config_manager = config_manager
        self.name = "BasePlugin"
        self.display_name = "Base Plugin"  # Human-readable name for reports
        self.description = "Abstract base class for KAST plugins."
        self.scan_type = "passive"  # or "active"
        self.output_type = "stdout"  # or "file"
        self.dependencies = []  # List of dependency specifications
        
        # Register schema and load configuration
        if self.config_manager:
            self.config_manager.register_plugin_schema(self.name, self.config_schema)
            self.config = self._load_config()
        else:
            self.config = {}

    def _load_config(self):
        """
        Load and validate plugin configuration.
        
        This method loads configuration from the ConfigManager, merges with
        CLI overrides, and validates against the plugin's schema.
        
        :return: Dictionary of configuration values
        """
        if not self.config_manager:
            return {}
        
        # Get merged config (file + CLI overrides)
        config = self.config_manager.get_plugin_config(self.name)
        
        # Validate config
        is_valid, errors = self.config_manager.validate_plugin_config(self.name, config)
        if not is_valid:
            self.debug(f"Configuration validation warnings for {self.name}:")
            for error in errors:
                self.debug(f"  - {error}")
        
        return config
    
    def get_config(self, key, default=None):
        """
        Get a configuration value with optional default.
        
        :param key: Configuration key
        :param default: Default value if key not found
        :return: Configuration value or default
        """
        return self.config.get(key, default)
    
    def setup(self, target, output_dir):
        """
        Optional setup step before running the plugin.
        Override in subclasses if needed.
        """
        pass

    def check_dependencies(self, previous_results):
        """
        Check if dependencies are satisfied based on previous plugin results.

        :param previous_results: Dictionary of results from previously run plugins
        :return: (bool, str) - (True/False if dependencies are met, reason if not)
        """
        if not self.dependencies:
            return True, ""

        for dep in self.dependencies:
            plugin_name = dep.get('plugin')
            condition = dep.get('condition')

            if plugin_name not in previous_results:
                return False, f"Dependent plugin '{plugin_name}' has not run yet"

            dep_result = previous_results[plugin_name]

            if not callable(condition):
                return False, f"Condition for dependency '{plugin_name}' is not callable"

            if not condition(dep_result):
                return False, f"Condition for dependency '{plugin_name}' not satisfied"

        return True, ""

    @abstractmethod
    def run(self, target, output_dir, report_only):
        """
        Run the plugin scan.
        :param target: The target domain or IP to scan.
        :param output_dir: Directory to write output files, if applicable.
        :param report_only: If True, do not execute the scan, only generate reports.
        :return: results dictionary
        """
        return self.get_result_dict("fail", "Not implemented.")

    def debug(self, message):
        """
        Print debug messages if verbose mode is enabled.
        """
        if getattr(self.cli_args, "verbose", False):
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-4]  # Truncate to hundredths of a second
            print(f"[{ts}] [DEBUG] [{self.name}]: {message}")

    def get_metadata(self):
        """
        Return plugin metadata as a dictionary.
        """
        return {
            "name": self.name,
            "display_name": getattr(self, 'display_name', self.name),
            "description": self.description,
            "scan_type": self.scan_type,
            "output_type": self.output_type,
            "priority": self.priority,
        }

    def get_result_dict(self, disposition, results, timestamp=None):
        """
        Standardized result dictionary for all plugins.
        :param disposition: 'success' or 'fail'
        :param results: plugin output (string, dict, etc.)
        :param timestamp: optional override for timestamp
        :return: dict
        """
        return {
            "name": self.name,
            "timestamp": timestamp or datetime.utcnow().isoformat(timespec="milliseconds"),
            "disposition": disposition,
            "results": results,
        }

    @abstractmethod
    def is_available(self):
        """
        Check if the required tool for this plugin is available.
        :return: True if available, False otherwise.
        """
        pass

    @abstractmethod
    def post_process(self, raw_output, output_dir):
        """
        Post-process the raw output from the plugin.
        
        This method should normalize the plugin output and extract key information
        for reporting. The processed output should be saved as a JSON file with
        the following standard fields:
        
        Required fields:
        - plugin-name: The plugin's name (self.name)
        - plugin-description: The plugin's description
        - plugin-display-name: Human-readable name (self.display_name)
        - timestamp: ISO format timestamp
        - findings: The raw or normalized findings data
        - summary: Human-readable summary of findings (use _generate_summary())
        - details: Formatted multi-line string with key details
        - issues: List of identified issues (empty list if none)
        - executive_summary: High-level summary for executive reports
        
        :param raw_output: Raw output (string, dict, or file path)
        :param output_dir: Directory to write processed JSON
        :return: Path to processed JSON file
        """
        pass

    def _generate_summary(self, findings):
        """
        Generate a human-readable summary from plugin findings.
        
        This method provides a default implementation that can be overridden
        in subclasses to provide tool-specific summaries. The summary should
        be a concise, human-readable description of what was found.
        
        Example overrides:
        - For vulnerability scanners: "Found 3 high, 5 medium, 2 low severity issues"
        - For WAF detection: "Detected WAF: Cloudflare"
        - For subdomain enumeration: "Discovered 42 subdomains"
        
        :param findings: Raw or processed findings (dict, list, or other)
        :return: str summary of findings
        """
        if not findings:
            return f"No findings were produced by {self.name}."
        elif isinstance(findings, dict):
            return f"{self.name} produced {len(findings)} top-level fields."
        elif isinstance(findings, list):
            return f"{self.name} produced {len(findings)} result items."
        else:
            return f"{self.name} produced findings of type: {type(findings).__name__}"
