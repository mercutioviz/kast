"""
Test unified config system for ZAP plugin

Verifies that ZAP plugin searches config files in the same order as ConfigManager
"""

import unittest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestZapUnifiedConfig(unittest.TestCase):
    """Test ZAP plugin unified config search paths"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        
    def test_config_search_order(self):
        """Test that ZAP searches configs in correct priority order"""
        # Create mock configs at different locations
        project_config = {
            'plugins': {
                'zap': {
                    'execution_mode': 'project',
                    'local': {'api_port': 8081}
                }
            }
        }
        
        user_config = {
            'plugins': {
                'zap': {
                    'execution_mode': 'user',
                    'local': {'api_port': 8082}
                }
            }
        }
        
        system_config = {
            'plugins': {
                'zap': {
                    'execution_mode': 'system',
                    'local': {'api_port': 8083}
                }
            }
        }
        
        standalone_config = {
            'execution_mode': 'standalone',
            'local': {'api_port': 8084}
        }
        
        # Test priority: project > user > system > standalone
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create project config
            project_path = Path(tmpdir) / 'kast_config.yaml'
            with open(project_path, 'w') as f:
                yaml.dump(project_config, f)
            
            # Mock Path.cwd to return our temp directory
            with patch('pathlib.Path.cwd', return_value=Path(tmpdir)):
                # Import after patching to use mocked paths
                from kast.plugins.zap_plugin import ZapPlugin
                
                class MockArgs:
                    verbose = True
                
                # Create plugin instance (should load project config)
                with patch.object(Path, 'expanduser', return_value=Path(tmpdir)):
                    plugin = ZapPlugin(MockArgs())
                    config = plugin._load_config()
                
                # Verify project config was loaded (highest priority)
                self.assertEqual(config['execution_mode'], 'project')
                self.assertEqual(config['local']['api_port'], 8081)
    
    def test_unified_format_parsing(self):
        """Test parsing unified config format (plugins.zap section)"""
        unified_config = {
            'kast': {'config_version': '1.1'},
            'plugins': {
                'zap': {
                    'execution_mode': 'local',
                    'local': {
                        'docker_image': 'custom:latest',
                        'api_port': 9090
                    }
                }
            }
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / 'kast_config.yaml'
            with open(config_path, 'w') as f:
                yaml.dump(unified_config, f)
            
            # Load and verify
            with open(config_path, 'r') as f:
                loaded = yaml.safe_load(f)
            
            self.assertIn('plugins', loaded)
            self.assertIn('zap', loaded['plugins'])
            self.assertEqual(loaded['plugins']['zap']['execution_mode'], 'local')
    
    def test_standalone_format_backward_compat(self):
        """Test that standalone zap_config.yaml still works (backward compat)"""
        standalone_config = {
            'execution_mode': 'remote',
            'remote': {
                'api_url': 'http://zap:8080',
                'api_key': 'test-key'
            }
        }
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create standalone config in expected location
            config_dir = Path(tmpdir) / 'config'
            config_dir.mkdir()
            config_path = config_dir / 'zap_config.yaml'
            
            with open(config_path, 'w') as f:
                yaml.dump(standalone_config, f)
            
            # Verify it parses correctly
            with open(config_path, 'r') as f:
                loaded = yaml.safe_load(f)
            
            self.assertEqual(loaded['execution_mode'], 'remote')
            self.assertEqual(loaded['remote']['api_key'], 'test-key')
    
    def test_legacy_cloud_config_adaptation(self):
        """Test that legacy zap_cloud_config.yaml is adapted correctly"""
        from kast.plugins.zap_plugin import ZapPlugin
        
        class MockArgs:
            verbose = True
        
        plugin = ZapPlugin(MockArgs())
        
        # Legacy cloud config format (no execution_mode key)
        legacy_config = {
            'cloud_provider': 'aws',
            'aws': {
                'region': 'us-east-1',
                'instance_type': 't3.medium'
            },
            'zap_config': {
                'timeout_minutes': 60
            }
        }
        
        # Adapt to new format
        adapted = plugin._adapt_legacy_config(legacy_config)
        
        # Verify adaptation
        self.assertEqual(adapted['execution_mode'], 'cloud')
        self.assertIn('cloud', adapted)
        self.assertEqual(adapted['cloud']['cloud_provider'], 'aws')
        self.assertEqual(adapted['zap_config']['timeout_minutes'], 60)
    
    def test_config_not_found_error(self):
        """Test that clear error is raised when no config found"""
        from kast.plugins.zap_plugin import ZapPlugin
        
        class MockArgs:
            verbose = False
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Patch all config paths to non-existent locations
            with patch('pathlib.Path.expanduser', return_value=Path(tmpdir) / 'nonexistent'):
                with patch('pathlib.Path.exists', return_value=False):
                    plugin = ZapPlugin(MockArgs())
                    
                    # Should raise FileNotFoundError with helpful message
                    with self.assertRaises(FileNotFoundError) as cm:
                        plugin._load_config()
                    
                    # Error message should list searched paths
                    error_msg = str(cm.exception)
                    self.assertIn('ZAP config not found', error_msg)
                    self.assertIn('Searched:', error_msg)


if __name__ == '__main__':
    unittest.main()
