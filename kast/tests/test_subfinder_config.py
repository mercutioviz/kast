"""
Test Subfinder plugin configuration integration.

This test verifies that the Subfinder plugin properly:
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

from plugins.subfinder_plugin import SubfinderPlugin
from config_manager import ConfigManager


class TestSubfinderConfig(unittest.TestCase):
    """Test Subfinder plugin configuration integration."""
    
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
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("subfinder", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["subfinder"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "Subfinder Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("sources", properties)
        self.assertIn("exclude_sources", properties)
        self.assertIn("use_all_sources", properties)
        self.assertIn("recursive_only", properties)
        self.assertIn("rate_limit", properties)
        self.assertIn("timeout", properties)
        self.assertIn("max_time", properties)
        self.assertIn("concurrent_goroutines", properties)
        self.assertIn("proxy", properties)
        self.assertIn("collect_sources", properties)
        self.assertIn("active_only", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.sources, [])
        self.assertEqual(plugin.exclude_sources, [])
        self.assertEqual(plugin.use_all_sources, False)
        self.assertEqual(plugin.recursive_only, False)
        self.assertEqual(plugin.rate_limit, 0)
        self.assertEqual(plugin.timeout, 30)
        self.assertEqual(plugin.max_time, 10)
        self.assertEqual(plugin.concurrent_goroutines, 10)
        self.assertIsNone(plugin.proxy)
        self.assertEqual(plugin.collect_sources, True)
        self.assertEqual(plugin.active_only, False)
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "sources": ["crtsh", "github", "virustotal"],
                    "exclude_sources": ["alienvault"],
                    "use_all_sources": False,
                    "recursive_only": True,
                    "rate_limit": 50,
                    "timeout": 60,
                    "max_time": 15,
                    "concurrent_goroutines": 20,
                    "proxy": "http://proxy.example.com:8080",
                    "collect_sources": False,
                    "active_only": True
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.sources, ["crtsh", "github", "virustotal"])
        self.assertEqual(plugin.exclude_sources, ["alienvault"])
        self.assertEqual(plugin.use_all_sources, False)
        self.assertEqual(plugin.recursive_only, True)
        self.assertEqual(plugin.rate_limit, 50)
        self.assertEqual(plugin.timeout, 60)
        self.assertEqual(plugin.max_time, 15)
        self.assertEqual(plugin.concurrent_goroutines, 20)
        self.assertEqual(plugin.proxy, "http://proxy.example.com:8080")
        self.assertEqual(plugin.collect_sources, False)
        self.assertEqual(plugin.active_only, True)
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "rate_limit": 10,
                    "timeout": 30,
                    "max_time": 5
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "subfinder": {
                "rate_limit": 100,
                "timeout": 120,
                "max_time": 20
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.rate_limit, 100)
        self.assertEqual(plugin.timeout, 120)
        self.assertEqual(plugin.max_time, 20)
    
    def test_command_building_with_defaults(self):
        """Test that commands are built correctly with default config."""
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes default values
        self.assertIn("subfinder", command)
        self.assertIn("-d example.com", command)
        self.assertIn("-cs", command)  # collect_sources=True
        self.assertIn("-oJ", command)  # JSON output
        self.assertNotIn("-all", command)  # use_all_sources=False
        self.assertNotIn("-nW", command)  # active_only=False
        self.assertNotIn("-s ", command)  # No specific sources
        self.assertNotIn("-rl ", command)  # rate_limit=0
    
    def test_command_building_with_custom_sources(self):
        """Test command building with custom sources."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "sources": ["crtsh", "github", "virustotal"]
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify sources are included
        self.assertIn("-s crtsh,github,virustotal", command)
    
    def test_command_building_with_exclude_sources(self):
        """Test command building with excluded sources."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "exclude_sources": ["alienvault", "shodan"]
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify excluded sources are included
        self.assertIn("-es alienvault,shodan", command)
    
    def test_command_building_with_all_sources(self):
        """Test command building with all sources enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "use_all_sources": True
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify -all flag is included
        self.assertIn("-all", command)
    
    def test_command_building_with_rate_limit(self):
        """Test command building with rate limit."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "rate_limit": 50
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify rate limit is included
        self.assertIn("-rl 50", command)
    
    def test_command_building_with_custom_timeouts(self):
        """Test command building with custom timeout values."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "timeout": 60,
                    "max_time": 20
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify timeouts are included
        self.assertIn("-timeout 60", command)
        self.assertIn("-max-time 20", command)
    
    def test_command_building_with_proxy(self):
        """Test command building with proxy configuration."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "proxy": "http://proxy.example.com:8080"
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify proxy is included
        self.assertIn("-proxy http://proxy.example.com:8080", command)
    
    def test_command_building_with_active_only(self):
        """Test command building with active_only enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "active_only": True
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify -nW flag is included
        self.assertIn("-nW", command)
    
    def test_command_building_without_collect_sources(self):
        """Test command building with collect_sources disabled."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "collect_sources": False
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify -cs flag is NOT included
        self.assertNotIn("-cs", command)
    
    def test_command_building_with_concurrent_goroutines(self):
        """Test command building with custom concurrent goroutines."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "concurrent_goroutines": 50
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify -t flag is included with custom value
        self.assertIn("-t 50", command)
    
    def test_operations_description(self):
        """Test that operations description reflects config values."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "sources": ["crtsh", "github"],
                    "rate_limit": 100,
                    "timeout": 90,
                    "max_time": 15
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes config values
        self.assertIn("sources: crtsh, github", operations)
        self.assertIn("rate limit: 100/s", operations)
        self.assertIn("timeout: 90s", operations)
        self.assertIn("max time: 15m", operations)
    
    def test_operations_description_with_all_sources(self):
        """Test operations description when using all sources."""
        self.config_manager.config_data = {
            "plugins": {
                "subfinder": {
                    "use_all_sources": True
                }
            }
        }
        
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations mentions all sources
        self.assertIn("all sources", operations)
    
    def test_schema_export(self):
        """Test that plugin schema can be exported."""
        plugin = SubfinderPlugin(self.cli_args, self.config_manager)
        
        # Export schema as JSON
        import json
        schema_json = self.config_manager.export_schema("json")
        schema = json.loads(schema_json)
        
        # Verify subfinder plugin is in exported schema
        self.assertIn("subfinder", schema["plugins"])
        
        # Verify schema properties
        subfinder_schema = schema["plugins"]["subfinder"]
        self.assertEqual(subfinder_schema["title"], "Subfinder Configuration")
        
        # Verify defaults are in schema
        props = subfinder_schema["properties"]
        self.assertEqual(props["sources"]["default"], [])
        self.assertEqual(props["use_all_sources"]["default"], False)
        self.assertEqual(props["rate_limit"]["default"], 0)
        self.assertEqual(props["timeout"]["default"], 30)
        self.assertEqual(props["max_time"]["default"], 10)
        self.assertEqual(props["concurrent_goroutines"]["default"], 10)


if __name__ == "__main__":
    unittest.main()
