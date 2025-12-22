"""
Test WhatWeb plugin configuration integration.

This test verifies that the WhatWeb plugin properly:
1. Registers its configuration schema
2. Loads configuration values from ConfigManager
3. Uses configuration values when building commands
"""

import unittest
import sys
import os
from unittest.mock import Mock, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.whatweb_plugin import WhatWebPlugin
from config_manager import ConfigManager


class TestWhatWebConfig(unittest.TestCase):
    """Test WhatWeb plugin configuration integration."""
    
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
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("whatweb", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["whatweb"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "WhatWeb Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("aggression_level", properties)
        self.assertIn("timeout", properties)
        self.assertIn("user_agent", properties)
        self.assertIn("follow_redirects", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.aggression_level, 3)
        self.assertEqual(plugin.timeout, 30)
        self.assertIsNone(plugin.user_agent)
        self.assertEqual(plugin.follow_redirects, 2)
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "whatweb": {
                    "aggression_level": 1,
                    "timeout": 60,
                    "user_agent": "Custom Agent",
                    "follow_redirects": 5
                }
            }
        }
        
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.aggression_level, 1)
        self.assertEqual(plugin.timeout, 60)
        self.assertEqual(plugin.user_agent, "Custom Agent")
        self.assertEqual(plugin.follow_redirects, 5)
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "whatweb": {
                    "aggression_level": 1,
                    "timeout": 60
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "whatweb": {
                "aggression_level": 4,
                "timeout": 120
            }
        }
        
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.aggression_level, 4)
        self.assertEqual(plugin.timeout, 120)
    
    def test_command_building_with_defaults(self):
        """Test that commands are built correctly with default config."""
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes default values
        self.assertIn("-a 3", command)  # Default aggression
        self.assertIn("--read-timeout 30", command)  # Default timeout
        self.assertIn("--max-redirects 2", command)  # Default redirects
        self.assertNotIn("--user-agent", command)  # No custom user agent
        
        # Verify argument order: target must come LAST
        self.assertTrue(command.endswith("https://example.com"))
    
    def test_command_building_with_custom_config(self):
        """Test that commands are built correctly with custom config."""
        # Set custom config
        self.config_manager.config_data = {
            "plugins": {
                "whatweb": {
                    "aggression_level": 1,
                    "timeout": 45,
                    "user_agent": "TestAgent/1.0",
                    "follow_redirects": 3
                }
            }
        }
        
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes custom values
        self.assertIn("-a 1", command)
        self.assertIn("--read-timeout 45", command)
        self.assertIn("--user-agent TestAgent/1.0", command)
        self.assertIn("--max-redirects 3", command)
    
    def test_operations_description(self):
        """Test that operations description reflects config values."""
        self.config_manager.config_data = {
            "plugins": {
                "whatweb": {
                    "aggression_level": 2,
                    "timeout": 90,
                    "follow_redirects": 1
                }
            }
        }
        
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes config values
        self.assertIn("aggression level 2", operations)
        self.assertIn("timeout 90s", operations)
        self.assertIn("max redirects 1", operations)
    
    def test_schema_export(self):
        """Test that plugin schema can be exported."""
        plugin = WhatWebPlugin(self.cli_args, self.config_manager)
        
        # Export schema as JSON
        import json
        schema_json = self.config_manager.export_schema("json")
        schema = json.loads(schema_json)
        
        # Verify whatweb plugin is in exported schema
        self.assertIn("whatweb", schema["plugins"])
        
        # Verify schema properties
        whatweb_schema = schema["plugins"]["whatweb"]
        self.assertEqual(whatweb_schema["title"], "WhatWeb Configuration")
        
        # Verify defaults are in schema
        props = whatweb_schema["properties"]
        self.assertEqual(props["aggression_level"]["default"], 3)
        self.assertEqual(props["timeout"]["default"], 30)
        self.assertEqual(props["follow_redirects"]["default"], 2)


if __name__ == "__main__":
    unittest.main()
