"""
Test ZAP plugin configuration integration.

This test verifies that the ZAP plugin properly:
1. Registers its hierarchical configuration schema
2. Supports CLI overrides for strategic parameters
3. Handles nested configuration values
"""

import unittest
import sys
import os
from unittest.mock import Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plugins.zap_plugin import ZapPlugin
from config_manager import ConfigManager


class TestZapConfig(unittest.TestCase):
    """Test ZAP plugin configuration integration."""
    
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
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        # Verify schema was registered
        self.assertIn("zap", self.config_manager.plugin_schemas)
        
        # Verify schema structure
        schema = self.config_manager.plugin_schemas["zap"]
        self.assertEqual(schema["type"], "object")
        self.assertEqual(schema["title"], "OWASP ZAP Configuration")
        
        # Verify all expected top-level properties exist
        properties = schema["properties"]
        self.assertIn("execution_mode", properties)
        self.assertIn("auto_discovery", properties)
        self.assertIn("local", properties)
        self.assertIn("remote", properties)
        self.assertIn("cloud", properties)
        self.assertIn("zap_config", properties)
    
    def test_schema_execution_modes(self):
        """Test that execution mode enum is properly defined."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["zap"]
        exec_mode = schema["properties"]["execution_mode"]
        
        # Verify enum values
        self.assertEqual(exec_mode["enum"], ["auto", "local", "remote", "cloud"])
        self.assertEqual(exec_mode["default"], "auto")
    
    def test_schema_local_mode_properties(self):
        """Test that local mode schema has all properties."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["zap"]
        local_props = schema["properties"]["local"]["properties"]
        
        # Verify local mode properties
        self.assertIn("docker_image", local_props)
        self.assertIn("auto_start", local_props)
        self.assertIn("api_port", local_props)
        self.assertIn("cleanup_on_completion", local_props)
        
        # Verify defaults
        self.assertEqual(local_props["docker_image"]["default"], "ghcr.io/zaproxy/zaproxy:stable")
        self.assertEqual(local_props["auto_start"]["default"], True)
        self.assertEqual(local_props["api_port"]["default"], 8080)
        self.assertEqual(local_props["cleanup_on_completion"]["default"], False)
    
    def test_schema_remote_mode_properties(self):
        """Test that remote mode schema has all properties."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["zap"]
        remote_props = schema["properties"]["remote"]["properties"]
        
        # Verify remote mode properties
        self.assertIn("api_url", remote_props)
        self.assertIn("timeout_seconds", remote_props)
        self.assertIn("verify_ssl", remote_props)
        
        # Verify defaults
        self.assertEqual(remote_props["timeout_seconds"]["default"], 30)
        self.assertEqual(remote_props["verify_ssl"]["default"], True)
    
    def test_schema_cloud_mode_properties(self):
        """Test that cloud mode schema has cloud provider enum."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["zap"]
        cloud_props = schema["properties"]["cloud"]["properties"]
        
        # Verify cloud provider property
        self.assertIn("cloud_provider", cloud_props)
        self.assertEqual(cloud_props["cloud_provider"]["enum"], ["aws", "azure", "gcp"])
        self.assertEqual(cloud_props["cloud_provider"]["default"], "aws")
    
    def test_schema_common_zap_settings(self):
        """Test that common ZAP settings are in schema."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        schema = self.config_manager.plugin_schemas["zap"]
        zap_props = schema["properties"]["zap_config"]["properties"]
        
        # Verify common settings
        self.assertIn("timeout_minutes", zap_props)
        self.assertIn("poll_interval_seconds", zap_props)
        self.assertIn("report_name", zap_props)
        
        # Verify defaults
        self.assertEqual(zap_props["timeout_minutes"]["default"], 60)
        self.assertEqual(zap_props["poll_interval_seconds"]["default"], 30)
        self.assertEqual(zap_props["report_name"]["default"], "zap_report.json")
    
    def test_set_nested_value(self):
        """Test setting nested values in config dictionary."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        config = {}
        
        # Test setting top-level value
        plugin._set_nested_value(config, 'execution_mode', 'local')
        self.assertEqual(config['execution_mode'], 'local')
        
        # Test setting nested value (one level)
        plugin._set_nested_value(config, 'local.api_port', 8081)
        self.assertEqual(config['local']['api_port'], 8081)
        
        # Test setting nested value (two levels)
        plugin._set_nested_value(config, 'zap_config.timeout_minutes', 120)
        self.assertEqual(config['zap_config']['timeout_minutes'], 120)
        
        # Test setting nested value in existing structure
        plugin._set_nested_value(config, 'local.docker_image', 'custom:latest')
        self.assertEqual(config['local']['docker_image'], 'custom:latest')
        self.assertEqual(config['local']['api_port'], 8081)  # Unchanged
    
    def test_apply_cli_overrides_execution_mode(self):
        """Test applying CLI override for execution mode."""
        # Set up ConfigManager mock to return override value
        self.config_manager.get_config = Mock(
            side_effect=lambda plugin_name, key: 'local' if key == 'execution_mode' else None
        )
        
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        config = {'execution_mode': 'auto'}
        result = plugin._apply_cli_overrides(config)
        
        self.assertEqual(result['execution_mode'], 'local')
    
    def test_apply_cli_overrides_nested_values(self):
        """Test applying CLI overrides for nested values."""
        # Set up ConfigManager mock to return override values
        def mock_get_config(plugin_name, key):
            overrides = {
                'local.api_port': 9090,
                'local.docker_image': 'custom-zap:v1',
                'zap_config.timeout_minutes': 180
            }
            return overrides.get(key)
        
        self.config_manager.get_config = Mock(side_effect=mock_get_config)
        
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        config = {
            'local': {
                'api_port': 8080,
                'docker_image': 'ghcr.io/zaproxy/zaproxy:stable'
            },
            'zap_config': {
                'timeout_minutes': 60
            }
        }
        
        result = plugin._apply_cli_overrides(config)
        
        self.assertEqual(result['local']['api_port'], 9090)
        self.assertEqual(result['local']['docker_image'], 'custom-zap:v1')
        self.assertEqual(result['zap_config']['timeout_minutes'], 180)
    
    def test_environment_variable_expansion(self):
        """Test that environment variables are expanded in config."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        # Set environment variables
        os.environ['TEST_ZAP_URL'] = 'http://zap.example.com:8080'
        os.environ['TEST_ZAP_KEY'] = 'secret-key-123'
        
        try:
            config = {
                'remote': {
                    'api_url': '${TEST_ZAP_URL}',
                    'api_key': '${TEST_ZAP_KEY}'
                },
                'regular_value': 'no expansion'
            }
            
            result = plugin._expand_env_vars(config)
            
            self.assertEqual(result['remote']['api_url'], 'http://zap.example.com:8080')
            self.assertEqual(result['remote']['api_key'], 'secret-key-123')
            self.assertEqual(result['regular_value'], 'no expansion')
            
        finally:
            del os.environ['TEST_ZAP_URL']
            del os.environ['TEST_ZAP_KEY']
    
    def test_environment_variable_missing(self):
        """Test that missing env vars are left as-is."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        config = {
            'remote': {
                'api_url': '${NONEXISTENT_VAR}'
            }
        }
        
        result = plugin._expand_env_vars(config)
        
        # Should keep the placeholder if env var doesn't exist
        self.assertEqual(result['remote']['api_url'], '${NONEXISTENT_VAR}')
    
    def test_legacy_config_adaptation(self):
        """Test that legacy cloud config is adapted to new format."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        legacy_config = {
            'cloud_provider': 'aws',
            'zap_config': {
                'timeout_minutes': 90
            },
            'tags': {
                'Project': 'Test'
            }
        }
        
        adapted = plugin._adapt_legacy_config(legacy_config)
        
        # Verify adaptation
        self.assertEqual(adapted['execution_mode'], 'cloud')
        self.assertIn('cloud', adapted)
        self.assertIn('zap_config', adapted)
        self.assertIn('tags', adapted)
    
    def test_plugin_metadata(self):
        """Test that plugin metadata is correctly set."""
        plugin = ZapPlugin(self.cli_args, self.config_manager)
        
        # Verify plugin metadata
        self.assertEqual(plugin.name, "zap")
        self.assertEqual(plugin.display_name, "OWASP ZAP")
        self.assertEqual(plugin.scan_type, "active")
        self.assertEqual(plugin.output_type, "file")
        self.assertEqual(plugin.priority, 200)
        self.assertIsNotNone(plugin.description)
        self.assertIsNotNone(plugin.website_url)


if __name__ == '__main__':
    unittest.main()
