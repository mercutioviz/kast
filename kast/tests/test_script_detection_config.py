"""
Test Script Detection plugin configuration integration.

This test verifies that the Script Detection plugin properly:
1. Registers its configuration schema
2. Loads configuration values from ConfigManager
3. Uses configuration values when making HTTP requests and analyzing scripts
"""

import unittest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.script_detection_plugin import ScriptDetectionPlugin
from config_manager import ConfigManager


class TestScriptDetectionConfig(unittest.TestCase):
    """Test Script Detection plugin configuration integration."""
    
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
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("script_detection", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["script_detection"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "Script Detection Configuration")
        
        # Verify all expected properties exist
        properties = schema["properties"]
        self.assertIn("request_timeout", properties)
        self.assertIn("user_agent", properties)
        self.assertIn("verify_ssl", properties)
        self.assertIn("follow_redirects", properties)
        self.assertIn("max_redirects", properties)
        self.assertIn("max_scripts_to_analyze", properties)
        self.assertIn("custom_headers", properties)
    
    def test_default_configuration(self):
        """Test that plugin loads default values from schema."""
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify defaults
        self.assertEqual(plugin.request_timeout, 30)
        self.assertEqual(plugin.user_agent, "KAST-Security-Scanner/1.0")
        self.assertEqual(plugin.verify_ssl, True)
        self.assertEqual(plugin.follow_redirects, True)
        self.assertEqual(plugin.max_redirects, 10)
        self.assertIsNone(plugin.max_scripts_to_analyze)
        self.assertEqual(plugin.custom_headers, {})
    
    def test_config_from_file(self):
        """Test loading configuration from config file."""
        # Simulate config file data
        self.config_manager.config_data = {
            "plugins": {
                "script_detection": {
                    "request_timeout": 60,
                    "user_agent": "Custom-Agent/2.0",
                    "verify_ssl": False,
                    "follow_redirects": False,
                    "max_redirects": 5,
                    "max_scripts_to_analyze": 50,
                    "custom_headers": {
                        "X-Custom-Header": "value",
                        "Authorization": "Bearer token"
                    }
                }
            }
        }
        
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify config values were loaded
        self.assertEqual(plugin.request_timeout, 60)
        self.assertEqual(plugin.user_agent, "Custom-Agent/2.0")
        self.assertEqual(plugin.verify_ssl, False)
        self.assertEqual(plugin.follow_redirects, False)
        self.assertEqual(plugin.max_redirects, 5)
        self.assertEqual(plugin.max_scripts_to_analyze, 50)
        self.assertEqual(plugin.custom_headers, {
            "X-Custom-Header": "value",
            "Authorization": "Bearer token"
        })
    
    def test_cli_overrides(self):
        """Test that CLI overrides take precedence over config file."""
        # Set up config file values
        self.config_manager.config_data = {
            "plugins": {
                "script_detection": {
                    "request_timeout": 30,
                    "user_agent": "Config-Agent/1.0",
                    "verify_ssl": True
                }
            }
        }
        
        # Set up CLI overrides
        self.config_manager.cli_overrides = {
            "script_detection": {
                "request_timeout": 90,
                "user_agent": "CLI-Agent/3.0",
                "verify_ssl": False
            }
        }
        
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify CLI overrides take precedence
        self.assertEqual(plugin.request_timeout, 90)
        self.assertEqual(plugin.user_agent, "CLI-Agent/3.0")
        self.assertEqual(plugin.verify_ssl, False)
    
    def test_timeout_configuration(self):
        """Test that request timeout is properly configured."""
        test_timeouts = [5, 30, 60, 120]
        
        for timeout in test_timeouts:
            self.config_manager.config_data = {
                "plugins": {
                    "script_detection": {
                        "request_timeout": timeout
                    }
                }
            }
            
            plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
            
            # Verify timeout is set correctly
            self.assertEqual(plugin.request_timeout, timeout)
    
    def test_ssl_verification_configuration(self):
        """Test that SSL verification can be toggled."""
        for verify_ssl in [True, False]:
            self.config_manager.config_data = {
                "plugins": {
                    "script_detection": {
                        "verify_ssl": verify_ssl
                    }
                }
            }
            
            plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
            
            # Verify SSL setting is correct
            self.assertEqual(plugin.verify_ssl, verify_ssl)
    
    def test_redirect_configuration(self):
        """Test that redirect behavior can be configured."""
        test_cases = [
            (True, 10),
            (False, 0),
            (True, 30),
            (True, 5)
        ]
        
        for follow_redirects, max_redirects in test_cases:
            self.config_manager.config_data = {
                "plugins": {
                    "script_detection": {
                        "follow_redirects": follow_redirects,
                        "max_redirects": max_redirects
                    }
                }
            }
            
            plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
            
            # Verify redirect settings
            self.assertEqual(plugin.follow_redirects, follow_redirects)
            self.assertEqual(plugin.max_redirects, max_redirects)
    
    def test_max_scripts_configuration(self):
        """Test that max_scripts_to_analyze can be configured."""
        test_cases = [None, 10, 50, 100, 500]
        
        for max_scripts in test_cases:
            self.config_manager.config_data = {
                "plugins": {
                    "script_detection": {
                        "max_scripts_to_analyze": max_scripts
                    }
                }
            }
            
            plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
            
            # Verify max_scripts is set correctly
            self.assertEqual(plugin.max_scripts_to_analyze, max_scripts)
    
    def test_custom_headers_configuration(self):
        """Test that custom headers can be configured."""
        test_cases = [
            {},
            {"X-Custom": "value"},
            {"Authorization": "Bearer token", "X-API-Key": "secret"},
            {"Accept-Language": "en-US", "X-Debug": "true"}
        ]
        
        for headers in test_cases:
            self.config_manager.config_data = {
                "plugins": {
                    "script_detection": {
                        "custom_headers": headers
                    }
                }
            }
            
            plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
            
            # Verify custom headers are set correctly
            self.assertEqual(plugin.custom_headers, headers)
    
    def test_user_agent_configuration(self):
        """Test that user agent can be customized."""
        test_agents = [
            "KAST-Security-Scanner/1.0",
            "Mozilla/5.0 (Custom)",
            "MyCustomAgent/2.0",
            "Research-Bot"
        ]
        
        for user_agent in test_agents:
            self.config_manager.config_data = {
                "plugins": {
                    "script_detection": {
                        "user_agent": user_agent
                    }
                }
            }
            
            plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
            
            # Verify user agent is set correctly
            self.assertEqual(plugin.user_agent, user_agent)
    
    def test_schema_constraints(self):
        """Test that schema properly defines constraints."""
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["script_detection"]
        properties = schema["properties"]
        
        # Test request_timeout constraints
        timeout_prop = properties["request_timeout"]
        self.assertEqual(timeout_prop["minimum"], 5)
        self.assertEqual(timeout_prop["maximum"], 120)
        self.assertEqual(timeout_prop["default"], 30)
        
        # Test max_redirects constraints
        redirects_prop = properties["max_redirects"]
        self.assertEqual(redirects_prop["minimum"], 0)
        self.assertEqual(redirects_prop["maximum"], 30)
        self.assertEqual(redirects_prop["default"], 10)
        
        # Test max_scripts_to_analyze constraints
        max_scripts_prop = properties["max_scripts_to_analyze"]
        self.assertEqual(max_scripts_prop["type"], ["integer", "null"])
        self.assertIsNone(max_scripts_prop["default"])
        self.assertEqual(max_scripts_prop["minimum"], 1)
        
        # Test boolean defaults
        self.assertEqual(properties["verify_ssl"]["default"], True)
        self.assertEqual(properties["follow_redirects"]["default"], True)
        
        # Test custom_headers type
        headers_prop = properties["custom_headers"]
        self.assertEqual(headers_prop["type"], "object")
        self.assertEqual(headers_prop["default"], {})
    
    def test_schema_export(self):
        """Test that plugin schema can be exported."""
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Export schema as JSON
        import json
        schema_json = self.config_manager.export_schema("json")
        schema = json.loads(schema_json)
        
        # Verify script_detection plugin is in exported schema
        self.assertIn("script_detection", schema["plugins"])
        
        # Verify schema properties
        sd_schema = schema["plugins"]["script_detection"]
        self.assertEqual(sd_schema["title"], "Script Detection Configuration")
        
        # Verify defaults are in schema
        props = sd_schema["properties"]
        self.assertEqual(props["request_timeout"]["default"], 30)
        self.assertEqual(props["user_agent"]["default"], "KAST-Security-Scanner/1.0")
        self.assertEqual(props["verify_ssl"]["default"], True)
        self.assertEqual(props["follow_redirects"]["default"], True)
        self.assertEqual(props["max_redirects"]["default"], 10)
        self.assertIsNone(props["max_scripts_to_analyze"]["default"])
        self.assertEqual(props["custom_headers"]["default"], {})
    
    def test_plugin_metadata(self):
        """Test that plugin metadata is correctly set."""
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify plugin metadata
        self.assertEqual(plugin.name, "script_detection")
        self.assertEqual(plugin.display_name, "External Script Detection")
        self.assertEqual(plugin.scan_type, "passive")
        self.assertEqual(plugin.output_type, "stdout")
        self.assertIsNotNone(plugin.description)
        self.assertIsNotNone(plugin.website_url)
    
    def test_dependency_configuration(self):
        """Test that plugin dependencies are properly configured."""
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify dependency on mozilla_observatory
        self.assertEqual(len(plugin.dependencies), 1)
        dependency = plugin.dependencies[0]
        self.assertEqual(dependency['plugin'], 'mozilla_observatory')
        self.assertIn('condition', dependency)
    
    def test_config_inheritance_order(self):
        """Test that config values follow correct precedence order."""
        # Precedence: CLI override > Config file > Schema default
        
        # Set config file value
        self.config_manager.config_data = {
            "plugins": {
                "script_detection": {
                    "request_timeout": 45
                }
            }
        }
        
        # No CLI override, should use config file value
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        self.assertEqual(plugin.request_timeout, 45)
        
        # Add CLI override, should take precedence
        self.config_manager.cli_overrides = {
            "script_detection": {
                "request_timeout": 90
            }
        }
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        self.assertEqual(plugin.request_timeout, 90)
        
        # Remove both, should use schema default
        self.config_manager.config_data = {"plugins": {}}
        self.config_manager.cli_overrides = {}
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        self.assertEqual(plugin.request_timeout, 30)  # Default from schema
    
    def test_combined_configuration(self):
        """Test that multiple config options work together."""
        self.config_manager.config_data = {
            "plugins": {
                "script_detection": {
                    "request_timeout": 60,
                    "user_agent": "TestAgent/1.0",
                    "verify_ssl": False,
                    "follow_redirects": True,
                    "max_redirects": 15,
                    "max_scripts_to_analyze": 25,
                    "custom_headers": {
                        "X-Test": "value"
                    }
                }
            }
        }
        
        plugin = ScriptDetectionPlugin(self.cli_args, self.config_manager)
        
        # Verify all values are set correctly
        self.assertEqual(plugin.request_timeout, 60)
        self.assertEqual(plugin.user_agent, "TestAgent/1.0")
        self.assertEqual(plugin.verify_ssl, False)
        self.assertEqual(plugin.follow_redirects, True)
        self.assertEqual(plugin.max_redirects, 15)
        self.assertEqual(plugin.max_scripts_to_analyze, 25)
        self.assertEqual(plugin.custom_headers, {"X-Test": "value"})


if __name__ == "__main__":
    unittest.main()
