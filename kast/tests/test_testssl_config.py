"""
Test configuration system for testssl plugin

This test suite verifies that the testssl plugin's configuration system works correctly,
including schema definition, default values, config file loading, CLI overrides, and
that config values are actually used in execution.
"""
import unittest
import tempfile
import shutil
import sys
import os
from unittest.mock import MagicMock, patch

# Add kast to path
sys.path.insert(0, '/opt/kast')

from kast.config_manager import ConfigManager
from kast.plugins.testssl_plugin import TestsslPlugin
from kast.tests.helpers.config_test_helpers import (
    create_test_config_file,
    assert_config_values,
    verify_schema_completeness,
    verify_type_match,
    get_schema_defaults,
    validate_config_against_schema
)


class TestTestsslConfig(unittest.TestCase):
    """Test suite for testssl plugin configuration system"""
    
    def setUp(self):
        """Set up test fixtures before each test"""
        self.mock_args = MagicMock()
        self.mock_args.verbose = False
        self.mock_args.config = None
        self.mock_args.set = None
        self.temp_dirs = []
    
    def tearDown(self):
        """Clean up after each test"""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_schema_defined_and_valid(self):
        """Verify plugin has valid config_schema with required fields"""
        plugin = TestsslPlugin(self.mock_args)
        
        # Schema must exist
        self.assertIsNotNone(plugin.config_schema)
        self.assertIsInstance(plugin.config_schema, dict)
        
        # Schema must have required JSON Schema fields
        self.assertEqual(plugin.config_schema.get("type"), "object")
        self.assertIn("properties", plugin.config_schema)
        self.assertIn("title", plugin.config_schema)
        self.assertIn("description", plugin.config_schema)
        
        # Verify schema completeness using helper
        errors = verify_schema_completeness(plugin.config_schema, "testssl")
        self.assertEqual(errors, [], f"Schema validation errors: {errors}")
        
        # All properties must have defaults
        properties = plugin.config_schema["properties"]
        for key, prop in properties.items():
            self.assertIn("default", prop, 
                f"Property '{key}' missing default value")
            self.assertIn("type", prop,
                f"Property '{key}' missing type definition")
            self.assertIn("description", prop,
                f"Property '{key}' missing description")
    
    def test_expected_config_properties(self):
        """Verify testssl has all expected config properties"""
        plugin = TestsslPlugin(self.mock_args)
        properties = plugin.config_schema["properties"]
        
        # Expected properties from migration
        expected_props = [
            "timeout",
            "test_vulnerabilities",
            "test_ciphers",
            "connect_timeout",
            "warnings_batch_mode"
        ]
        
        for prop in expected_props:
            self.assertIn(prop, properties,
                f"Expected property '{prop}' not found in schema")
    
    def test_default_values_loaded(self):
        """Verify defaults from schema are loaded when no config provided"""
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl", 
            TestsslPlugin.config_schema)
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify each config property has the schema default
        expected_defaults = {
            "timeout": 300,
            "test_vulnerabilities": True,
            "test_ciphers": True,
            "connect_timeout": 10,
            "warnings_batch_mode": True
        }
        
        assert_config_values(plugin, expected_defaults)
    
    def test_config_file_overrides_defaults(self):
        """Verify YAML config file values override schema defaults"""
        # Create test config file with non-default values
        config_path, temp_dir = create_test_config_file({
            "testssl": {
                "timeout": 600,
                "test_vulnerabilities": False,
                "test_ciphers": False,
                "connect_timeout": 30,
                "warnings_batch_mode": False
            }
        })
        self.temp_dirs.append(temp_dir)
        
        # Load config and create plugin
        self.mock_args.config = config_path
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        config_manager.load(config_path)
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify config file values were loaded
        expected_values = {
            "timeout": 600,
            "test_vulnerabilities": False,
            "test_ciphers": False,
            "connect_timeout": 30,
            "warnings_batch_mode": False
        }
        
        assert_config_values(plugin, expected_values)
    
    def test_cli_overrides_config_file(self):
        """Verify --set CLI overrides take precedence over config file"""
        # Create base config file
        config_path, temp_dir = create_test_config_file({
            "testssl": {
                "timeout": 600,
                "test_ciphers": False
            }
        })
        self.temp_dirs.append(temp_dir)
        
        # Set CLI overrides
        self.mock_args.config = config_path
        self.mock_args.set = [
            "testssl.timeout=900",
            "testssl.test_ciphers=true"
        ]
        
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        config_manager.load(config_path)
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify CLI overrides were applied
        self.assertEqual(plugin.timeout, 900)
        self.assertEqual(plugin.test_ciphers, True)
    
    def test_type_validation(self):
        """Verify config values have correct types"""
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify each property has the correct Python type
        schema_props = TestsslPlugin.config_schema["properties"]
        for key, prop in schema_props.items():
            plugin_value = getattr(plugin, key, None)
            expected_type = prop["type"]
            
            is_valid, error = verify_type_match(plugin_value, expected_type)
            self.assertTrue(is_valid,
                f"{key}: Type mismatch - {error}")
    
    def test_config_values_used_in_command_building(self):
        """Verify config values actually affect command generation"""
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        
        # Test with custom config values
        self.mock_args.set = [
            "testssl.test_vulnerabilities=false",
            "testssl.test_ciphers=false",
            "testssl.connect_timeout=20",
            "testssl.warnings_batch_mode=false"
        ]
        config_manager.load()
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify config was loaded
        self.assertEqual(plugin.test_vulnerabilities, False)
        self.assertEqual(plugin.test_ciphers, False)
        self.assertEqual(plugin.connect_timeout, 20)
        self.assertEqual(plugin.warnings_batch_mode, False)
        
        # Simulate command building by calling run() in report-only mode
        # This won't actually execute, but will build the command
        temp_dir = tempfile.mkdtemp()
        self.temp_dirs.append(temp_dir)
        
        # Create a dummy result file for report-only mode
        result_file = os.path.join(temp_dir, "testssl.json")
        with open(result_file, 'w') as f:
            f.write('{"scanResult": []}')
        
        result = plugin.run("example.com", temp_dir, report_only=True)
        
        # Check the command that would be executed
        # With test_vulnerabilities=false and test_ciphers=false,
        # the command should NOT have -U or -E flags
        command = plugin.command_executed
        self.assertIsNotNone(command, "Command should be set")
        
        # Verify flags are NOT present when disabled
        self.assertNotIn("-U", command, "Should not have -U flag when vulnerabilities disabled")
        self.assertNotIn("-E", command, "Should not have -E flag when ciphers disabled")
        
        # Verify connect timeout is present
        self.assertIn("--connect-timeout", command)
        self.assertIn("20", command)
        
        # Verify warnings flag is NOT present when disabled
        self.assertNotIn("--warnings=batch", command)
    
    def test_flags_present_when_enabled(self):
        """Verify flags ARE present in command when config enables them"""
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        
        # Use defaults (all true)
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify config has defaults
        self.assertEqual(plugin.test_vulnerabilities, True)
        self.assertEqual(plugin.test_ciphers, True)
        self.assertEqual(plugin.warnings_batch_mode, True)
        
        # Build command
        temp_dir = tempfile.mkdtemp()
        self.temp_dirs.append(temp_dir)
        
        result_file = os.path.join(temp_dir, "testssl.json")
        with open(result_file, 'w') as f:
            f.write('{"scanResult": []}')
        
        plugin.run("example.com", temp_dir, report_only=True)
        command = plugin.command_executed
        
        # Verify flags ARE present when enabled
        self.assertIn("-U", command, "Should have -U flag when vulnerabilities enabled")
        self.assertIn("-E", command, "Should have -E flag when ciphers enabled")
        self.assertIn("--warnings=batch", command, "Should have warnings flag when enabled")
    
    def test_timeout_enforcement(self):
        """Verify timeout config is passed to subprocess execution"""
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        
        # Set custom timeout
        self.mock_args.set = ["testssl.timeout=250"]
        config_manager.load()
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        self.assertEqual(plugin.timeout, 250)
        
        # Mock subprocess.run to capture timeout parameter
        temp_dir = tempfile.mkdtemp()
        self.temp_dirs.append(temp_dir)
        
        with patch('subprocess.run') as mock_run:
            # Configure mock to return success
            mock_run.return_value = MagicMock(returncode=0)
            
            # Create mock output file
            result_file = os.path.join(temp_dir, "testssl.json")
            with open(result_file, 'w') as f:
                f.write('{"scanResult": [{"id": "test"}]}')
            
            plugin.run("example.com", temp_dir, report_only=False)
            
            # Verify subprocess.run was called with timeout parameter
            self.assertTrue(mock_run.called)
            call_kwargs = mock_run.call_args[1]
            self.assertIn('timeout', call_kwargs)
            self.assertEqual(call_kwargs['timeout'], 250)
    
    def test_numeric_constraints_validation(self):
        """Verify min/max constraints are properly defined"""
        schema_props = TestsslPlugin.config_schema["properties"]
        
        # Check timeout constraints
        timeout_prop = schema_props["timeout"]
        self.assertEqual(timeout_prop["minimum"], 60)
        self.assertEqual(timeout_prop["maximum"], 1800)
        self.assertEqual(timeout_prop["default"], 300)
        self.assertGreaterEqual(timeout_prop["default"], timeout_prop["minimum"])
        self.assertLessEqual(timeout_prop["default"], timeout_prop["maximum"])
        
        # Check connect_timeout constraints
        connect_prop = schema_props["connect_timeout"]
        self.assertEqual(connect_prop["minimum"], 5)
        self.assertEqual(connect_prop["maximum"], 60)
        self.assertEqual(connect_prop["default"], 10)
        self.assertGreaterEqual(connect_prop["default"], connect_prop["minimum"])
        self.assertLessEqual(connect_prop["default"], connect_prop["maximum"])
    
    def test_invalid_config_values_detected(self):
        """Verify invalid config values are detected by validation"""
        schema = TestsslPlugin.config_schema
        
        # Test value below minimum
        errors = validate_config_against_schema(
            {"timeout": 30},  # Below minimum of 60
            schema
        )
        self.assertTrue(len(errors) > 0, "Should detect value below minimum")
        self.assertTrue(any("below minimum" in err for err in errors))
        
        # Test value above maximum
        errors = validate_config_against_schema(
            {"timeout": 2000},  # Above maximum of 1800
            schema
        )
        self.assertTrue(len(errors) > 0, "Should detect value above maximum")
        self.assertTrue(any("above maximum" in err for err in errors))
        
        # Test wrong type
        errors = validate_config_against_schema(
            {"timeout": "not a number"},
            schema
        )
        self.assertTrue(len(errors) > 0, "Should detect wrong type")
    
    def test_boolean_config_handling(self):
        """Verify boolean config values are handled correctly"""
        config_path, temp_dir = create_test_config_file({
            "testssl": {
                "test_vulnerabilities": True,
                "test_ciphers": False
            }
        })
        self.temp_dirs.append(temp_dir)
        
        config_manager = ConfigManager(self.mock_args)
        config_manager.register_plugin_schema("testssl",
            TestsslPlugin.config_schema)
        config_manager.load(config_path)
        
        plugin = TestsslPlugin(self.mock_args, config_manager)
        
        # Verify boolean values
        self.assertIsInstance(plugin.test_vulnerabilities, bool)
        self.assertIsInstance(plugin.test_ciphers, bool)
        self.assertEqual(plugin.test_vulnerabilities, True)
        self.assertEqual(plugin.test_ciphers, False)
    
    def test_schema_defaults_extraction(self):
        """Verify we can extract all defaults from schema"""
        defaults = get_schema_defaults(TestsslPlugin.config_schema)
        
        expected_defaults = {
            "timeout": 300,
            "test_vulnerabilities": True,
            "test_ciphers": True,
            "connect_timeout": 10,
            "warnings_batch_mode": True
        }
        
        self.assertEqual(defaults, expected_defaults)
    
    def test_no_legacy_cli_args(self):
        """Verify testssl has no legacy CLI arguments to maintain"""
        # TestSSL was migrated without any existing CLI arguments
        # This test documents that fact
        plugin = TestsslPlugin(self.mock_args)
        
        # If legacy args existed, we'd test them here
        # For now, just verify plugin initializes correctly without them
        self.assertIsNotNone(plugin)
        self.assertEqual(plugin.name, "testssl")


if __name__ == '__main__':
    unittest.main()
