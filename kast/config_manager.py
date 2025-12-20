"""
Configuration management for KAST plugins.

This module handles loading, merging, and validating plugin configurations
from YAML files and CLI arguments. It provides a centralized way to manage
plugin settings and export schemas for GUI tools like kast-web.
"""

import yaml
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import defaultdict


class ConfigManager:
    """
    Manages configuration loading, validation, and schema export for KAST plugins.
    
    Configuration priority (highest to lowest):
    1. CLI overrides (--set plugin.key=value)
    2. CLI arguments (legacy --httpx-rate-limit)
    3. Project-specific config (./kast_config.yaml)
    4. User config (~/.config/kast/config.yaml)
    5. System config (/etc/kast/config.yaml)
    6. Plugin defaults (from schema)
    """
    
    CONFIG_VERSION = "1.0"
    
    def __init__(self, cli_args=None, logger=None):
        """
        Initialize the configuration manager.
        
        :param cli_args: Parsed CLI arguments from argparse
        :param logger: Logger instance for debug/error messages
        """
        self.cli_args = cli_args
        self.logger = logger or logging.getLogger("kast.config")
        
        # Define config file search paths (in priority order)
        self.config_paths = [
            Path("./kast_config.yaml"),  # Project-specific
            Path.home() / ".config" / "kast" / "config.yaml",  # User config (XDG)
            Path("/etc/kast/config.yaml"),  # System-wide
        ]
        
        # Loaded configuration data
        self.config_data = {
            "kast": {"config_version": self.CONFIG_VERSION},
            "global": {},
            "plugins": {}
        }
        
        # Plugin schemas (populated by plugins during registration)
        self.plugin_schemas = {}
        
        # CLI overrides parsed from --set arguments
        self.cli_overrides = {}
        
    def load(self, config_file: Optional[str] = None) -> bool:
        """
        Load configuration from file or default locations.
        
        :param config_file: Specific config file path (from --config arg)
        :return: True if config loaded successfully, False otherwise
        """
        loaded_file = None
        
        # If specific config file provided, try to load it
        if config_file:
            config_path = Path(config_file).expanduser()
            if config_path.exists():
                try:
                    self.config_data = self._load_yaml_file(config_path)
                    loaded_file = config_path
                    self.logger.info(f"Loaded config from: {config_path}")
                except Exception as e:
                    self.logger.error(f"Failed to load config from {config_path}: {e}")
                    return False
            else:
                self.logger.warning(f"Config file not found: {config_path}")
                return False
        else:
            # Try default locations in priority order
            for config_path in self.config_paths:
                config_path = config_path.expanduser()
                if config_path.exists():
                    try:
                        self.config_data = self._load_yaml_file(config_path)
                        loaded_file = config_path
                        self.logger.info(f"Loaded config from: {config_path}")
                        break
                    except Exception as e:
                        self.logger.warning(f"Failed to load config from {config_path}: {e}")
                        continue
        
        # Parse CLI overrides (--set arguments)
        if self.cli_args and hasattr(self.cli_args, 'set') and self.cli_args.set:
            self._parse_cli_overrides(self.cli_args.set)
        
        if loaded_file:
            self.logger.debug(f"Configuration loaded from {loaded_file}")
            return True
        else:
            self.logger.debug("No configuration file found, using defaults")
            return False
    
    def _load_yaml_file(self, path: Path) -> Dict[str, Any]:
        """
        Load and parse a YAML configuration file.
        
        :param path: Path to YAML file
        :return: Parsed configuration dictionary
        """
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
        
        # Ensure required top-level keys exist
        if not isinstance(data, dict):
            raise ValueError("Config file must contain a YAML dictionary")
        
        if "plugins" not in data:
            data["plugins"] = {}
        if "global" not in data:
            data["global"] = {}
        if "kast" not in data:
            data["kast"] = {"config_version": self.CONFIG_VERSION}
        
        return data
    
    def _parse_cli_overrides(self, set_args: List[str]) -> None:
        """
        Parse --set arguments into nested dictionary structure.
        
        Examples:
            --set related_sites.httpx_rate_limit=20
            --set testssl.timeout=600
        
        :param set_args: List of "plugin.key=value" strings
        """
        for arg in set_args:
            if '=' not in arg:
                self.logger.warning(f"Invalid --set format (missing '='): {arg}")
                continue
            
            key_path, value = arg.split('=', 1)
            parts = key_path.split('.')
            
            if len(parts) != 2:
                self.logger.warning(f"Invalid --set format (expected plugin.key=value): {arg}")
                continue
            
            plugin_name, config_key = parts
            
            # Try to parse value as appropriate type
            parsed_value = self._parse_value(value)
            
            # Store in overrides dictionary
            if plugin_name not in self.cli_overrides:
                self.cli_overrides[plugin_name] = {}
            self.cli_overrides[plugin_name][config_key] = parsed_value
            
            self.logger.debug(f"CLI override: {plugin_name}.{config_key} = {parsed_value}")
    
    def _parse_value(self, value: str) -> Any:
        """
        Parse string value into appropriate Python type.
        
        :param value: String value from CLI
        :return: Parsed value (int, float, bool, list, or str)
        """
        # Try boolean
        if value.lower() in ('true', 'yes', '1'):
            return True
        if value.lower() in ('false', 'no', '0'):
            return False
        
        # Try null
        if value.lower() in ('null', 'none', ''):
            return None
        
        # Try integer
        try:
            return int(value)
        except ValueError:
            pass
        
        # Try float
        try:
            return float(value)
        except ValueError:
            pass
        
        # Try list (comma-separated)
        if ',' in value:
            return [item.strip() for item in value.split(',')]
        
        # Default to string
        return value
    
    def register_plugin_schema(self, plugin_name: str, schema: Dict[str, Any]) -> None:
        """
        Register a plugin's configuration schema.
        
        :param plugin_name: Name of the plugin
        :param schema: JSON Schema dictionary defining config structure
        """
        self.plugin_schemas[plugin_name] = schema
        self.logger.debug(f"Registered schema for plugin: {plugin_name}")
    
    def get_plugin_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific plugin.
        
        Merges settings from:
        1. Plugin defaults (from schema)
        2. Config file
        3. CLI overrides
        
        :param plugin_name: Name of the plugin
        :return: Merged configuration dictionary
        """
        # Start with plugin defaults from schema
        config = self._get_defaults_from_schema(plugin_name)
        
        # Merge with config file settings
        if plugin_name in self.config_data.get("plugins", {}):
            config.update(self.config_data["plugins"][plugin_name])
        
        # Apply CLI overrides (highest priority)
        if plugin_name in self.cli_overrides:
            config.update(self.cli_overrides[plugin_name])
        
        return config
    
    def _get_defaults_from_schema(self, plugin_name: str) -> Dict[str, Any]:
        """
        Extract default values from a plugin's schema.
        
        :param plugin_name: Name of the plugin
        :return: Dictionary of default values
        """
        defaults = {}
        
        if plugin_name not in self.plugin_schemas:
            return defaults
        
        schema = self.plugin_schemas[plugin_name]
        properties = schema.get("properties", {})
        
        for key, prop_schema in properties.items():
            if "default" in prop_schema:
                defaults[key] = prop_schema["default"]
        
        return defaults
    
    def get_global_config(self) -> Dict[str, Any]:
        """
        Get global configuration settings.
        
        :return: Global configuration dictionary
        """
        return self.config_data.get("global", {})
    
    def export_schema(self, format: str = "json") -> str:
        """
        Export complete configuration schema for all registered plugins.
        
        This is used by GUI tools like kast-web to auto-generate forms.
        
        :param format: Output format ("json" or "yaml")
        :return: Serialized schema string
        """
        schema = {
            "kast": {
                "config_version": self.CONFIG_VERSION,
                "description": "KAST Configuration Schema"
            },
            "global": {
                "type": "object",
                "title": "Global Settings",
                "description": "Settings that apply to all plugins",
                "properties": {
                    "timeout": {
                        "type": "integer",
                        "default": 300,
                        "minimum": 30,
                        "description": "Default timeout in seconds for plugin execution"
                    },
                    "retry_count": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 0,
                        "maximum": 5,
                        "description": "Default number of retries for failed operations"
                    }
                }
            },
            "plugins": {}
        }
        
        # Add all registered plugin schemas
        for plugin_name, plugin_schema in self.plugin_schemas.items():
            schema["plugins"][plugin_name] = plugin_schema
        
        if format == "yaml":
            return yaml.dump(schema, default_flow_style=False, sort_keys=False)
        else:
            return json.dumps(schema, indent=2)
    
    def create_default_config(self, output_path: Optional[str] = None) -> str:
        """
        Create a default configuration file with all plugin options.
        
        :param output_path: Optional path for config file (default: ~/.config/kast/config.yaml)
        :return: Path to created config file
        """
        if output_path:
            config_path = Path(output_path).expanduser()
        else:
            config_path = Path.home() / ".config" / "kast" / "config.yaml"
        
        # Create directory if needed
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Build default config with all registered plugins
        default_config = {
            "kast": {
                "config_version": self.CONFIG_VERSION
            },
            "global": {
                "timeout": 300,
                "retry_count": 2
            },
            "plugins": {}
        }
        
        # Add defaults for each plugin from schemas
        for plugin_name in self.plugin_schemas:
            default_config["plugins"][plugin_name] = self._get_defaults_from_schema(plugin_name)
        
        # Write to file
        with open(config_path, 'w') as f:
            yaml.dump(
                default_config,
                f,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True
            )
        
        self.logger.info(f"Created default config at: {config_path}")
        return str(config_path)
    
    def show_current_config(self, plugin_name: Optional[str] = None) -> str:
        """
        Display current configuration (merged from all sources).
        
        :param plugin_name: Optional plugin name to show only that plugin's config
        :return: YAML string of current configuration
        """
        if plugin_name:
            # Show only specific plugin
            config = {
                "plugins": {
                    plugin_name: self.get_plugin_config(plugin_name)
                }
            }
        else:
            # Show full configuration
            config = {
                "kast": self.config_data.get("kast", {}),
                "global": self.get_global_config(),
                "plugins": {}
            }
            
            # Add all registered plugins
            for pname in self.plugin_schemas:
                config["plugins"][pname] = self.get_plugin_config(pname)
        
        return yaml.dump(config, default_flow_style=False, sort_keys=False)
    
    def validate_plugin_config(self, plugin_name: str, config: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate plugin configuration against its schema.
        
        :param plugin_name: Name of the plugin
        :param config: Configuration dictionary to validate
        :return: Tuple of (is_valid, list_of_errors)
        """
        errors = []
        
        if plugin_name not in self.plugin_schemas:
            return True, []  # No schema = no validation
        
        schema = self.plugin_schemas[plugin_name]
        properties = schema.get("properties", {})
        
        # Check each config value against schema
        for key, value in config.items():
            if key not in properties:
                errors.append(f"Unknown config key: {key}")
                continue
            
            prop_schema = properties[key]
            
            # Type validation
            expected_type = prop_schema.get("type")
            if expected_type:
                if not self._validate_type(value, expected_type):
                    errors.append(f"{key}: Expected type {expected_type}, got {type(value).__name__}")
            
            # Minimum/maximum validation for numbers
            if isinstance(value, (int, float)):
                if "minimum" in prop_schema and value < prop_schema["minimum"]:
                    errors.append(f"{key}: Value {value} below minimum {prop_schema['minimum']}")
                if "maximum" in prop_schema and value > prop_schema["maximum"]:
                    errors.append(f"{key}: Value {value} above maximum {prop_schema['maximum']}")
        
        return len(errors) == 0, errors
    
    def _validate_type(self, value: Any, expected_type: Any) -> bool:
        """
        Validate value type against JSON Schema type specification.
        
        :param value: Value to validate
        :param expected_type: JSON Schema type (string or list of strings)
        :return: True if type matches, False otherwise
        """
        # Handle list of allowed types (e.g., ["integer", "null"])
        if isinstance(expected_type, list):
            return any(self._validate_type(value, t) for t in expected_type)
        
        # Handle null
        if expected_type == "null":
            return value is None
        
        # Type mapping
        type_map = {
            "string": str,
            "integer": int,
            "number": (int, float),
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        expected_python_type = type_map.get(expected_type)
        if expected_python_type:
            return isinstance(value, expected_python_type)
        
        return True  # Unknown type = pass validation
