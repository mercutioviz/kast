#!/usr/bin/env python3

import os
import yaml
import logging
from pathlib import Path

# Default configuration file paths
DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "default_config.yaml")
USER_CONFIG_PATH = os.path.expanduser("~/.config/kast/config.yaml")
LOCAL_CONFIG_PATH = os.path.join(os.getcwd(), "kast_config.yaml")

class ConfigManager:
    """Configuration manager for KAST"""
    
    def __init__(self, config_path=None):
        """
        Initialize the configuration manager
        
        Args:
            config_path (str, optional): Path to a custom configuration file
        """
        self.logger = logging.getLogger("kast.config")
        self.config = {}
        self.config_path = config_path
        
        # Load configuration
        self.load_config()
    
    def load_config(self):
        """Load configuration from files"""
        # Start with default configuration
        self._load_file(DEFAULT_CONFIG_PATH)
        
        # Override with user configuration if it exists
        if os.path.exists(USER_CONFIG_PATH):
            self._load_file(USER_CONFIG_PATH)
        
        # Override with local configuration if it exists
        if os.path.exists(LOCAL_CONFIG_PATH):
            self._load_file(LOCAL_CONFIG_PATH)
        
        # Override with specified configuration if provided
        if self.config_path and os.path.exists(self.config_path):
            self._load_file(self.config_path)
        
        self.logger.debug(f"Configuration loaded from {self.config_path or 'default locations'}")
    
    def _load_file(self, file_path):
        """
        Load configuration from a YAML file
        
        Args:
            file_path (str): Path to the configuration file
        """
        try:
            with open(file_path, 'r') as f:
                config_data = yaml.safe_load(f)
                
            if config_data:
                # Update configuration recursively
                self._update_dict_recursive(self.config, config_data)
                self.logger.debug(f"Loaded configuration from {file_path}")
        except Exception as e:
            self.logger.error(f"Error loading configuration from {file_path}: {e}")
    
    def _update_dict_recursive(self, d, u):
        """
        Update dictionary recursively
        
        Args:
            d (dict): Dictionary to update
            u (dict): Dictionary with updates
        """
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                self._update_dict_recursive(d[k], v)
            else:
                d[k] = v
    
    def get(self, key, default=None):
        """
        Get a configuration value
        
        Args:
            key (str): Configuration key (dot notation for nested keys)
            default: Default value if key is not found
            
        Returns:
            The configuration value or default
        """
        keys = key.split('.')
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key, value):
        """
        Set a configuration value
        
        Args:
            key (str): Configuration key (dot notation for nested keys)
            value: Value to set
        """
        keys = key.split('.')
        config = self.config
        
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def save(self, file_path=None):
        """
        Save configuration to a file
        
        Args:
            file_path (str, optional): Path to save the configuration
        """
        if not file_path:
            file_path = USER_CONFIG_PATH
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        try:
            with open(file_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
            self.logger.debug(f"Configuration saved to {file_path}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving configuration to {file_path}: {e}")
            return False
    
    def get_api_key(self, service):
        """
        Get an API key for a service
        
        Args:
            service (str): Service name
            
        Returns:
            str: API key or None if not found
        """
        return self.get(f"api_keys.{service}")

# Global configuration instance
config = ConfigManager()

def get_config():
    """Get the global configuration instance"""
    return config

def load_config(config_path=None):
    """
    Load configuration from a file
    
    Args:
        config_path (str, optional): Path to the configuration file
        
    Returns:
        ConfigManager: Configuration manager instance
    """
    global config
    config = ConfigManager(config_path)
    return config
