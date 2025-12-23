"""
Test FTAP plugin configuration integration.

This test verifies that the FTAP plugin properly:
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

from plugins.ftap_plugin import FtapPlugin
from config_manager import ConfigManager


class TestFtapConfig(unittest.TestCase):
    """Test FTAP plugin configuration integration."""
    
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
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("ftap", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["ftap"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "FTAP Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("detection_mode", properties)
        self.assertIn("wordlist_path", properties)
        self.assertIn("update_wordlist", properties)
        self.assertIn("wordlist_source", properties)
        self.assertIn("machine_learning", properties)
        self.assertIn("fuzzing", properties)
        self.assertIn("http3", properties)
        self.assertIn("concurrency", properties)
        self.assertIn("export_format", properties)
        self.assertIn("interactive", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.detection_mode, "stealth")
        self.assertIsNone(plugin.wordlist_path)
        self.assertEqual(plugin.update_wordlist, False)
        self.assertIsNone(plugin.wordlist_source)
        self.assertEqual(plugin.machine_learning, False)
        self.assertEqual(plugin.fuzzing, False)
        self.assertEqual(plugin.http3, False)
        self.assertIsNone(plugin.concurrency)
        self.assertEqual(plugin.export_format, "json")
        self.assertEqual(plugin.interactive, False)
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "detection_mode": "aggressive",
                    "wordlist_path": "/path/to/custom/wordlist.txt",
                    "update_wordlist": True,
                    "wordlist_source": "https://example.com/wordlists",
                    "machine_learning": True,
                    "fuzzing": True,
                    "http3": True,
                    "concurrency": 150,
                    "export_format": "html",
                    "interactive": True
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.detection_mode, "aggressive")
        self.assertEqual(plugin.wordlist_path, "/path/to/custom/wordlist.txt")
        self.assertEqual(plugin.update_wordlist, True)
        self.assertEqual(plugin.wordlist_source, "https://example.com/wordlists")
        self.assertEqual(plugin.machine_learning, True)
        self.assertEqual(plugin.fuzzing, True)
        self.assertEqual(plugin.http3, True)
        self.assertEqual(plugin.concurrency, 150)
        self.assertEqual(plugin.export_format, "html")
        self.assertEqual(plugin.interactive, True)
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "detection_mode": "stealth",
                    "concurrency": 50,
                    "machine_learning": False
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "ftap": {
                "detection_mode": "aggressive",
                "concurrency": 150,
                "machine_learning": True
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.detection_mode, "aggressive")
        self.assertEqual(plugin.concurrency, 150)
        self.assertEqual(plugin.machine_learning, True)
    
    def test_command_building_with_defaults(self):
        """Test that commands are built correctly with default config."""
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify command includes default values
        self.assertIn("ftap", command)
        self.assertIn("--url example.com", command)
        self.assertIn("--detection-mode stealth", command)
        self.assertIn("-d /tmp/output", command)
        self.assertIn("-e json", command)
        self.assertIn("-f ftap.json", command)
        
        # Verify optional flags are not included
        self.assertNotIn("--machine-learning", command)
        self.assertNotIn("--fuzzing", command)
        self.assertNotIn("--http3", command)
        self.assertNotIn("--concurrency", command)
        self.assertNotIn("-w", command)
    
    def test_command_building_with_aggressive_mode(self):
        """Test command building with aggressive detection mode."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "detection_mode": "aggressive"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify aggressive mode is included
        self.assertIn("--detection-mode aggressive", command)
    
    def test_command_building_with_custom_wordlist(self):
        """Test command building with custom wordlist."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "wordlist_path": "/custom/admin_paths.txt"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify wordlist is included
        self.assertIn("-w /custom/admin_paths.txt", command)
    
    def test_command_building_with_wordlist_update(self):
        """Test command building with wordlist update enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "update_wordlist": True,
                    "wordlist_source": "https://github.com/example/wordlists"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify wordlist update flags are included
        self.assertIn("--update-wordlist", command)
        self.assertIn("--source https://github.com/example/wordlists", command)
    
    def test_command_building_with_machine_learning(self):
        """Test command building with machine learning enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "machine_learning": True
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify ML flag is included
        self.assertIn("--machine-learning", command)
    
    def test_command_building_with_fuzzing(self):
        """Test command building with fuzzing enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "fuzzing": True
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify fuzzing flag is included
        self.assertIn("--fuzzing", command)
    
    def test_command_building_with_http3(self):
        """Test command building with HTTP/3 support."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "http3": True
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify HTTP/3 flag is included
        self.assertIn("--http3", command)
    
    def test_command_building_with_concurrency(self):
        """Test command building with custom concurrency."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "concurrency": 150
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify concurrency is included
        self.assertIn("--concurrency 150", command)
    
    def test_command_building_with_html_export(self):
        """Test command building with HTML export format."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "export_format": "html"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify HTML export format is included
        self.assertIn("-e html", command)
        self.assertIn("-f ftap.html", command)
    
    def test_command_building_with_csv_export(self):
        """Test command building with CSV export format."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "export_format": "csv"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify CSV export format is included
        self.assertIn("-e csv", command)
        self.assertIn("-f ftap.csv", command)
    
    def test_command_building_with_interactive_mode(self):
        """Test command building with interactive mode enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "interactive": True
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify interactive flag is included
        self.assertIn("-i", command)
    
    def test_command_building_with_all_features(self):
        """Test command building with all features enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "detection_mode": "aggressive",
                    "wordlist_path": "/custom/wordlist.txt",
                    "machine_learning": True,
                    "fuzzing": True,
                    "http3": True,
                    "concurrency": 200,
                    "export_format": "html"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        command = dry_run_info["commands"][0]
        
        # Verify all flags are included
        self.assertIn("--detection-mode aggressive", command)
        self.assertIn("-w /custom/wordlist.txt", command)
        self.assertIn("--machine-learning", command)
        self.assertIn("--fuzzing", command)
        self.assertIn("--http3", command)
        self.assertIn("--concurrency 200", command)
        self.assertIn("-e html", command)
    
    def test_operations_description_default(self):
        """Test that operations description reflects default config."""
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes detection mode
        self.assertIn("stealth mode", operations)
    
    def test_operations_description_with_features(self):
        """Test operations description with multiple features enabled."""
        self.config_manager.config_data = {
            "plugins": {
                "ftap": {
                    "detection_mode": "aggressive",
                    "machine_learning": True,
                    "fuzzing": True,
                    "http3": True,
                    "concurrency": 150,
                    "wordlist_path": "/custom/paths.txt"
                }
            }
        }
        
        plugin = FtapPlugin(self.cli_args, self.config_manager)
        
        dry_run_info = plugin.get_dry_run_info("example.com", "/tmp/output")
        operations = dry_run_info["operations"]
        
        # Verify operations description includes all features
        self.assertIn("aggressive mode", operations)
        self.assertIn("machine learning", operations)
        self.assertIn("path fuzzing", operations)
        self.assertIn("HTTP/3", operations)
        self.assertIn("concurrency: 150", operations)
        self.assertIn("custom wordlist", operations)


if __name__ == "__main__":
    unittest.main()
