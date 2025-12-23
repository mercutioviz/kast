"""
Test Katana plugin configuration integration.

This test verifies that the Katana plugin properly:
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

from plugins.katana_plugin import KatanaPlugin
from config_manager import ConfigManager


class TestKatanaConfig(unittest.TestCase):
    """Test Katana plugin configuration integration."""
    
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
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("katana", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["katana"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "Katana Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("depth", properties)
        self.assertIn("js_crawl", properties)
        self.assertIn("crawl_duration", properties)
        self.assertIn("known_files", properties)
        self.assertIn("automatic_form_fill", properties)
        self.assertIn("strategy", properties)
        self.assertIn("concurrency", properties)
        self.assertIn("parallelism", properties)
        self.assertIn("rate_limit", properties)
        self.assertIn("delay", properties)
        self.assertIn("timeout", properties)
        self.assertIn("retry", properties)
        self.assertIn("proxy", properties)
        self.assertIn("field_scope", properties)
        self.assertIn("headless", properties)
        self.assertIn("xhr_extraction", properties)
        self.assertIn("extension_filter", properties)
        self.assertIn("omit_body", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.depth, 3)
        self.assertEqual(plugin.js_crawl, False)
        self.assertEqual(plugin.crawl_duration, 0)
        self.assertEqual(plugin.known_files, "")
        self.assertEqual(plugin.automatic_form_fill, False)
        self.assertEqual(plugin.strategy, "depth-first")
        self.assertEqual(plugin.concurrency, 10)
        self.assertEqual(plugin.parallelism, 10)
        self.assertEqual(plugin.rate_limit, 150)
        self.assertEqual(plugin.delay, 0)
        self.assertEqual(plugin.timeout, 10)
        self.assertEqual(plugin.retry, 1)
        self.assertIsNone(plugin.proxy)
        self.assertEqual(plugin.field_scope, "rdn")
        self.assertEqual(plugin.headless, False)
        self.assertEqual(plugin.xhr_extraction, False)
        self.assertEqual(plugin.extension_filter, [])
        self.assertEqual(plugin.omit_body, True)
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "depth": 5,
                    "js_crawl": True,
                    "crawl_duration": 300,
                    "known_files": "all",
                    "automatic_form_fill": True,
                    "strategy": "breadth-first",
                    "concurrency": 20,
                    "parallelism": 15,
                    "rate_limit": 100,
                    "delay": 2,
                    "timeout": 30,
                    "retry": 3,
                    "proxy": "http://proxy.example.com:8080",
                    "field_scope": "fqdn",
                    "headless": True,
                    "xhr_extraction": True,
                    "extension_filter": ["png", "jpg", "css"],
                    "omit_body": False
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.depth, 5)
        self.assertEqual(plugin.js_crawl, True)
        self.assertEqual(plugin.crawl_duration, 300)
        self.assertEqual(plugin.known_files, "all")
        self.assertEqual(plugin.automatic_form_fill, True)
        self.assertEqual(plugin.strategy, "breadth-first")
        self.assertEqual(plugin.concurrency, 20)
        self.assertEqual(plugin.parallelism, 15)
        self.assertEqual(plugin.rate_limit, 100)
        self.assertEqual(plugin.delay, 2)
        self.assertEqual(plugin.timeout, 30)
        self.assertEqual(plugin.retry, 3)
        self.assertEqual(plugin.proxy, "http://proxy.example.com:8080")
        self.assertEqual(plugin.field_scope, "fqdn")
        self.assertEqual(plugin.headless, True)
        self.assertEqual(plugin.xhr_extraction, True)
        self.assertEqual(plugin.extension_filter, ["png", "jpg", "css"])
        self.assertEqual(plugin.omit_body, False)
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "depth": 3,
                    "rate_limit": 100,
                    "timeout": 10
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "katana": {
                "depth": 7,
                "rate_limit": 200,
                "timeout": 60
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.depth, 7)
        self.assertEqual(plugin.rate_limit, 200)
        self.assertEqual(plugin.timeout, 60)
    
    def test_command_building_with_defaults(self):
        """Test that commands are built correctly with default config."""
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes default values
        self.assertIn("katana", command)
        self.assertIn("-silent", command)
        self.assertIn("-u example.com", command)
        self.assertIn("-ob", command)  # omit_body=True
        self.assertNotIn("-d ", command)  # depth=3 (default, not added)
        self.assertNotIn("-jc", command)  # js_crawl=False
        self.assertNotIn("-hl", command)  # headless=False
        self.assertNotIn("-rl ", command)  # rate_limit=150 (default, not added)
    
    def test_command_building_with_custom_depth(self):
        """Test command building with custom crawl depth."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "depth": 5
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify depth is included
        self.assertIn("-d 5", command)
    
    def test_command_building_with_js_crawl(self):
        """Test command building with JavaScript crawling enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "js_crawl": True
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify -jc flag is included
        self.assertIn("-jc", command)
    
    def test_command_building_with_crawl_duration(self):
        """Test command building with crawl duration limit."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "crawl_duration": 300
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify crawl duration is included
        self.assertIn("-ct 300s", command)
    
    def test_command_building_with_known_files(self):
        """Test command building with known files crawling."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "known_files": "all"
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify known files flag is included
        self.assertIn("-kf all", command)
    
    def test_command_building_with_form_fill(self):
        """Test command building with automatic form filling."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "automatic_form_fill": True
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify form fill flag is included
        self.assertIn("-aff", command)
    
    def test_command_building_with_breadth_first(self):
        """Test command building with breadth-first strategy."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "strategy": "breadth-first"
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify strategy is included
        self.assertIn("-s breadth-first", command)
    
    def test_command_building_with_concurrency(self):
        """Test command building with custom concurrency."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "concurrency": 25
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify concurrency is included
        self.assertIn("-c 25", command)
    
    def test_command_building_with_rate_limit(self):
        """Test command building with custom rate limit."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "rate_limit": 50
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify rate limit is included
        self.assertIn("-rl 50", command)
    
    def test_command_building_with_delay(self):
        """Test command building with request delay."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "delay": 2
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify delay is included
        self.assertIn("-rd 2", command)
    
    def test_command_building_with_timeout(self):
        """Test command building with custom timeout."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "timeout": 30
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify timeout is included
        self.assertIn("-timeout 30", command)
    
    def test_command_building_with_proxy(self):
        """Test command building with proxy configuration."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "proxy": "http://proxy.example.com:8080"
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify proxy is included
        self.assertIn("-proxy http://proxy.example.com:8080", command)
    
    def test_command_building_with_field_scope(self):
        """Test command building with custom field scope."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "field_scope": "fqdn"
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify field scope is included
        self.assertIn("-fs fqdn", command)
    
    def test_command_building_with_headless(self):
        """Test command building with headless mode enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "headless": True
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify headless flag is included
        self.assertIn("-hl", command)
    
    def test_command_building_with_xhr_extraction(self):
        """Test command building with XHR extraction enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "xhr_extraction": True
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify XHR flag is included
        self.assertIn("-xhr", command)
    
    def test_command_building_with_extension_filter(self):
        """Test command building with extension filtering."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "extension_filter": ["png", "jpg", "css", "woff"]
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify extension filter is included
        self.assertIn("-ef png,jpg,css,woff", command)
    
    def test_command_building_without_omit_body(self):
        """Test command building with omit_body disabled."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "omit_body": False
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify -ob flag is NOT included
        self.assertNotIn("-ob", command)
    
    def test_operations_description(self):
        """Test that operations description reflects config values."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "depth": 5,
                    "js_crawl": True,
                    "rate_limit": 100,
                    "timeout": 30,
                    "extension_filter": ["png", "css"]
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes config values
        self.assertIn("depth: 5", operations)
        self.assertIn("JS crawling", operations)
        self.assertIn("rate: 100/s", operations)
        self.assertIn("timeout: 30s", operations)
        self.assertIn("filtering: png, css", operations)
    
    def test_operations_description_with_headless(self):
        """Test operations description when headless mode is enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "katana": {
                    "headless": True
                }
            }
        }
        
        plugin = KatanaPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes headless mode
        self.assertIn("headless mode", operations)


if __name__ == "__main__":
    unittest.main()
