"""
Test Wafw00f plugin configuration integration.

This test verifies that the Wafw00f plugin properly:
1. Registers its configuration schema
2. Loads configuration values from ConfigManager
3. Uses configuration values when building commands
"""

import unittest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.wafw00f_plugin import Wafw00fPlugin
from config_manager import ConfigManager


class TestWafw00fConfig(unittest.TestCase):
    """Test Wafw00f plugin configuration integration."""
    
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
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("wafw00f", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["wafw00f"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "Wafw00f Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("find_all", properties)
        self.assertIn("verbosity", properties)
        self.assertIn("follow_redirects", properties)
        self.assertIn("timeout", properties)
        self.assertIn("proxy", properties)
        self.assertIn("test_specific_waf", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.find_all, True)
        self.assertEqual(plugin.verbosity, 3)
        self.assertEqual(plugin.follow_redirects, True)
        self.assertEqual(plugin.timeout, 30)
        self.assertIsNone(plugin.proxy)
        self.assertIsNone(plugin.test_specific_waf)
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "wafw00f": {
                    "find_all": False,
                    "verbosity": 1,
                    "follow_redirects": False,
                    "timeout": 60,
                    "proxy": "http://proxy.example.com:8080",
                    "test_specific_waf": "Cloudflare"
                }
            }
        }
        
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.find_all, False)
        self.assertEqual(plugin.verbosity, 1)
        self.assertEqual(plugin.follow_redirects, False)
        self.assertEqual(plugin.timeout, 60)
        self.assertEqual(plugin.proxy, "http://proxy.example.com:8080")
        self.assertEqual(plugin.test_specific_waf, "Cloudflare")
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "wafw00f": {
                    "find_all": False,
                    "verbosity": 1,
                    "timeout": 60
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "wafw00f": {
                "find_all": True,
                "verbosity": 3,
                "timeout": 120
            }
        }
        
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.find_all, True)
        self.assertEqual(plugin.verbosity, 3)
        self.assertEqual(plugin.timeout, 120)
    
    def test_command_building_with_defaults(self):
        """Test that commands are built correctly with default config."""
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes default values
        self.assertIn("-a", command)  # find_all=True
        self.assertIn("-vvv", command)  # verbosity=3
        self.assertIn("-T 30", command)  # timeout=30
        self.assertNotIn("-r", command)  # follow_redirects=True (no flag)
        self.assertNotIn("-p", command)  # No proxy
        self.assertNotIn("-t", command)  # No specific WAF test
    
    def test_command_building_with_custom_config(self):
        """Test that commands are built correctly with custom config."""
        # Set custom config
        self.config_manager.config_data = {
            "plugins": {
                "wafw00f": {
                    "find_all": False,
                    "verbosity": 1,
                    "follow_redirects": False,
                    "timeout": 45,
                    "proxy": "http://proxy:8080",
                    "test_specific_waf": "Cloudflare"
                }
            }
        }
        
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes custom values
        self.assertNotIn("-a", command)  # find_all=False
        self.assertIn("-v", command)  # verbosity=1
        self.assertIn("-r", command)  # follow_redirects=False
        self.assertIn("-T 45", command)  # timeout=45
        self.assertIn("-p http://proxy:8080", command)  # proxy set
        self.assertIn("-t Cloudflare", command)  # specific WAF test
    
    def test_verbosity_levels(self):
        """Test that verbosity flags are built correctly."""
        test_cases = [
            (0, ""),  # No verbosity flag
            (1, "-v"),
            (2, "-vv"),
            (3, "-vvv")
        ]
        
        for verbosity_level, expected_flag in test_cases:
            self.config_manager.config_data = {
                "plugins": {
                    "wafw00f": {
                        "verbosity": verbosity_level
                    }
                }
            }
            
            plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
            dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
            command = dry_run_info["commands"][0]
            
            if expected_flag:
                self.assertIn(expected_flag, command)
            else:
                # No verbosity flag should be present for level 0
                self.assertNotIn("-v", command)
    
    def test_operations_description(self):
        """Test that operations description reflects config values."""
        self.config_manager.config_data = {
            "plugins": {
                "wafw00f": {
                    "find_all": True,
                    "timeout": 90,
                    "test_specific_waf": "Cloudflare"
                }
            }
        }
        
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("https://example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes config values
        self.assertIn("test all WAF signatures", operations)
        self.assertIn("test for Cloudflare", operations)
        self.assertIn("timeout 90s", operations)
    
    def test_schema_export(self):
        """Test that plugin schema can be exported."""
        plugin = Wafw00fPlugin(self.cli_args, self.config_manager)
        
        # Export schema as JSON
        import json
        schema_json = self.config_manager.export_schema("json")
        schema = json.loads(schema_json)
        
        # Verify wafw00f plugin is in exported schema
        self.assertIn("wafw00f", schema["plugins"])
        
        # Verify schema properties
        wafw00f_schema = schema["plugins"]["wafw00f"]
        self.assertEqual(wafw00f_schema["title"], "Wafw00f Configuration")
        
        # Verify defaults are in schema
        props = wafw00f_schema["properties"]
        self.assertEqual(props["find_all"]["default"], True)
        self.assertEqual(props["verbosity"]["default"], 3)
        self.assertEqual(props["follow_redirects"]["default"], True)
        self.assertEqual(props["timeout"]["default"], 30)


if __name__ == "__main__":
    unittest.main()
