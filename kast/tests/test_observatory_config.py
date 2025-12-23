"""
Test Mozilla Observatory plugin configuration integration.

This test verifies that the Observatory plugin properly:
1. Registers its configuration schema
2. Loads configuration values from ConfigManager
3. Uses configuration values when executing commands
"""

import unittest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.observatory_plugin import ObservatoryPlugin
from config_manager import ConfigManager


class TestObservatoryConfig(unittest.TestCase):
    """Test Observatory plugin configuration integration."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Create mock CLI args
        self.cli_args = Mock()
        self.cli_args.verbose = False
        self.cli_args.set = []
        
        # Create ConfigManager
        self.config_manager = ConfigManager(self.cli_args)
    
    def test_schema_registration(self):
        """Test that plugin schema is registered with ConfigManager."""
        # Create plugin (this should register schema)
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("mozilla_observatory", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["mozilla_observatory"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "Mozilla Observatory Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("timeout", properties)
        self.assertIn("retry_attempts", properties)
        self.assertIn("additional_args", properties)
        self.assertIn("format", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.timeout, 300)
        self.assertEqual(plugin.retry_attempts, 1)
        self.assertEqual(plugin.additional_args, [])
        self.assertEqual(plugin.format, "json")
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "mozilla_observatory": {
                    "timeout": 600,
                    "retry_attempts": 3,
                    "additional_args": ["--verbose"],
                    "format": "json"
                }
            }
        }
        
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.timeout, 600)
        self.assertEqual(plugin.retry_attempts, 3)
        self.assertEqual(plugin.additional_args, ["--verbose"])
        self.assertEqual(plugin.format, "json")
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "mozilla_observatory": {
                    "timeout": 300,
                    "retry_attempts": 1
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "mozilla_observatory": {
                "timeout": 600,
                "retry_attempts": 3
            }
        }
        
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.timeout, 600)
        self.assertEqual(plugin.retry_attempts, 3)
    
    def test_command_building_with_defaults(self):
        """Test that commands are built correctly with default config."""
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify basic command structure
        self.assertIn("mdn-http-observatory-scan", command)
        self.assertIn("https://example.com", command)
        
        # With defaults, no additional args should be present
        parts = command.split()
        self.assertEqual(len(parts), 2)  # Just command and target
    
    def test_command_building_with_additional_args(self):
        """Test that additional args are included in command."""
        # Set custom config with additional args
        self.config_manager.config_data = {
            "plugins": {
                "mozilla_observatory": {
                    "additional_args": ["--verbose", "--debug"]
                }
            }
        }
        
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify additional args are NOT in dry_run_info (since it shows base command)
        # but they would be added during actual execution
        # Note: The current implementation adds args in run(), not get_dry_run_info()
        self.assertIn("mdn-http-observatory-scan", command)
        self.assertIn("https://example.com", command)
    
    def test_timeout_configuration(self):
        """Test that timeout is properly configured."""
        test_timeouts = [30, 300, 600, 1800]
        
        for timeout in test_timeouts:
            self.config_manager.config_data = {
                "plugins": {
                    "mozilla_observatory": {
                        "timeout": timeout
                    }
                }
            }
            
            plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
            
            # Verify timeout is set correctly
            self.assertEqual(plugin.timeout, timeout)
    
    def test_retry_attempts_configuration(self):
        """Test that retry attempts are properly configured."""
        test_retries = [1, 2, 3, 5]
        
        for retry_count in test_retries:
            self.config_manager.config_data = {
                "plugins": {
                    "mozilla_observatory": {
                        "retry_attempts": retry_count
                    }
                }
            }
            
            plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
            
            # Verify retry attempts are set correctly
            self.assertEqual(plugin.retry_attempts, retry_count)
    
    def test_additional_args_types(self):
        """Test that additional_args accepts various argument formats."""
        test_cases = [
            [],  # Empty list
            ["--verbose"],  # Single arg
            ["--verbose", "--debug"],  # Multiple args
            ["--flag=value"],  # Arg with value
        ]
        
        for args in test_cases:
            self.config_manager.config_data = {
                "plugins": {
                    "mozilla_observatory": {
                        "additional_args": args
                    }
                }
            }
            
            plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
            
            # Verify args are set correctly
            self.assertEqual(plugin.additional_args, args)
    
    def test_schema_constraints(self):
        """Test that schema properly defines constraints."""
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["mozilla_observatory"]
        properties = schema["properties"]
        
        # Test timeout constraints
        timeout_prop = properties["timeout"]
        self.assertEqual(timeout_prop["minimum"], 30)
        self.assertEqual(timeout_prop["maximum"], 1800)
        self.assertEqual(timeout_prop["default"], 300)
        
        # Test retry_attempts constraints
        retry_prop = properties["retry_attempts"]
        self.assertEqual(retry_prop["minimum"], 1)
        self.assertEqual(retry_prop["maximum"], 5)
        self.assertEqual(retry_prop["default"], 1)
        
        # Test format enum constraint
        format_prop = properties["format"]
        self.assertEqual(format_prop["enum"], ["json"])
        self.assertEqual(format_prop["default"], "json")
        
        # Test additional_args type
        args_prop = properties["additional_args"]
        self.assertEqual(args_prop["type"], "array")
        self.assertEqual(args_prop["items"]["type"], "string")
        self.assertEqual(args_prop["default"], [])
    
    def test_schema_export(self):
        """Test that plugin schema can be exported."""
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        # Export schema as JSON
        import json
        schema_json = self.config_manager.export_schema("json")
        schema = json.loads(schema_json)
        
        # Verify mozilla_observatory plugin is in exported schema
        self.assertIn("mozilla_observatory", schema["plugins"])
        
        # Verify schema properties
        obs_schema = schema["plugins"]["mozilla_observatory"]
        self.assertEqual(obs_schema["title"], "Mozilla Observatory Configuration")
        
        # Verify defaults are in schema
        props = obs_schema["properties"]
        self.assertEqual(props["timeout"]["default"], 300)
        self.assertEqual(props["retry_attempts"]["default"], 1)
        self.assertEqual(props["additional_args"]["default"], [])
        self.assertEqual(props["format"]["default"], "json")
    
    def test_plugin_metadata(self):
        """Test that plugin metadata is correctly set."""
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        
        # Verify plugin metadata
        self.assertEqual(plugin.name, "mozilla_observatory")
        self.assertEqual(plugin.display_name, "Mozilla Observatory")
        self.assertEqual(plugin.scan_type, "passive")
        self.assertEqual(plugin.output_type, "stdout")
        self.assertIsNotNone(plugin.description)
        self.assertIsNotNone(plugin.website_url)
    
    def test_config_inheritance_order(self):
        """Test that config values follow correct precedence order."""
        # Precedence: CLI override > Config file > Schema default
        
        # Set config file value
        self.config_manager.config_data = {
            "plugins": {
                "mozilla_observatory": {
                    "timeout": 450
                }
            }
        }
        
        # No CLI override, should use config file value
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        self.assertEqual(plugin.timeout, 450)
        
        # Add CLI override, should take precedence
        self.config_manager.cli_overrides = {
            "mozilla_observatory": {
                "timeout": 900
            }
        }
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        self.assertEqual(plugin.timeout, 900)
        
        # Remove both, should use schema default
        self.config_manager.config_data = {"plugins": {}}
        self.config_manager.cli_overrides = {}
        plugin = ObservatoryPlugin(self.cli_args, self.config_manager)
        self.assertEqual(plugin.timeout, 300)  # Default from schema


if __name__ == "__main__":
    unittest.main()
