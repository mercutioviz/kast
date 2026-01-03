"""
ZAP Provider Factory with Auto-Discovery
Determines the best available ZAP execution mode
"""

import os
import subprocess
from pathlib import Path

from kast.scripts.zap_providers import (
    LocalZapProvider,
    RemoteZapProvider,
    CloudZapProvider
)


class ZapProviderFactory:
    """Factory for creating ZAP instance providers with auto-discovery"""
    
    def __init__(self, config, debug_callback=None):
        """
        Initialize factory
        
        :param config: Configuration dictionary
        :param debug_callback: Optional callback for debug messages
        """
        self.config = config
        self.debug = debug_callback or (lambda x: None)
    
    def create_provider(self):
        """
        Create appropriate ZAP provider based on configuration
        
        :return: ZapInstanceProvider instance
        """
        execution_mode = self.config.get('execution_mode', 'auto')
        
        # Check if mode was explicitly set (not auto)
        is_explicit = execution_mode != 'auto'
        
        if is_explicit:
            self.debug(f"ZAP execution mode: {execution_mode} (explicit - skipping auto-discovery)")
        else:
            self.debug(f"ZAP execution mode: {execution_mode}")
        
        if execution_mode == 'auto':
            return self._auto_discover_provider()
        elif execution_mode == 'local':
            return LocalZapProvider(self.config, self.debug)
        elif execution_mode == 'remote':
            return RemoteZapProvider(self.config, self.debug)
        elif execution_mode == 'cloud':
            return CloudZapProvider(self.config, self.debug)
        else:
            self.debug(f"Unknown execution mode: {execution_mode}, using auto")
            return self._auto_discover_provider()
    
    def _auto_discover_provider(self):
        """
        Auto-discover the best available ZAP provider
        
        Priority:
        1. Check for environment variable with remote ZAP URL
        2. Check for running local ZAP container
        3. Check if Docker is available for local mode
        4. Fall back to cloud provisioning
        
        :return: ZapInstanceProvider instance
        """
        self.debug("Auto-discovering ZAP execution mode...")
        
        auto_config = self.config.get('auto_discovery', {})
        check_env_vars = auto_config.get('check_env_vars', True)
        prefer_local = auto_config.get('prefer_local', True)
        
        # 1. Check for remote ZAP via environment variables
        if check_env_vars and self._check_remote_env_vars():
            self.debug("Auto-discovery: Using remote mode (env vars found)")
            return RemoteZapProvider(self.config, self.debug)
        
        # 2. Check for local ZAP container or Docker availability
        if prefer_local and self._check_local_available():
            self.debug("Auto-discovery: Using local mode (Docker available)")
            return LocalZapProvider(self.config, self.debug)
        
        # 3. Fall back to cloud provisioning
        self.debug("Auto-discovery: Using cloud mode (fallback)")
        return CloudZapProvider(self.config, self.debug)
    
    def _check_remote_env_vars(self):
        """
        Check if remote ZAP configuration is available via environment variables
        
        :return: True if KAST_ZAP_URL is set
        """
        zap_url = os.environ.get('KAST_ZAP_URL')
        if zap_url:
            self.debug(f"Found KAST_ZAP_URL: {zap_url}")
            return True
        return False
    
    def _check_local_available(self):
        """
        Check if local ZAP mode is available
        
        Checks:
        1. Docker is installed
        2. (Optionally) ZAP container is already running
        
        :return: True if local mode is available
        """
        # Check if Docker is available
        try:
            result = subprocess.run(['docker', '--version'],
                                   capture_output=True,
                                   text=True,
                                   timeout=5)
            if result.returncode == 0:
                self.debug("Docker is available for local mode")
                return True
        except Exception as e:
            self.debug(f"Docker check failed: {e}")
        
        return False
    
    def _check_running_zap_container(self):
        """
        Check if a ZAP container is already running
        
        :return: True if ZAP container found
        """
        try:
            result = subprocess.run(['docker', 'ps', '--filter', 'ancestor=ghcr.io/zaproxy/zaproxy',
                                    '--format', '{{.Names}}'],
                                   capture_output=True,
                                   text=True,
                                   timeout=5)
            if result.returncode == 0 and result.stdout.strip():
                self.debug("Found running ZAP container")
                return True
        except Exception as e:
            self.debug(f"Container check failed: {e}")
        
        return False


def get_provider_capabilities():
    """
    Get information about available providers and their requirements
    
    :return: Dictionary with provider capabilities
    """
    return {
        'local': {
            'name': 'Local Docker',
            'description': 'Uses local Docker container',
            'requires': ['Docker'],
            'cost': 'Free',
            'speed': 'Fast',
            'isolation': 'Low'
        },
        'remote': {
            'name': 'Remote Instance',
            'description': 'Connects to existing ZAP instance',
            'requires': ['ZAP URL', 'Network access'],
            'cost': 'Variable',
            'speed': 'Fast',
            'isolation': 'Medium'
        },
        'cloud': {
            'name': 'Cloud Provisioning',
            'description': 'Provisions ephemeral cloud infrastructure',
            'requires': ['Terraform', 'Cloud credentials'],
            'cost': '$0.02-0.07/hour',
            'speed': 'Slow (provisioning)',
            'isolation': 'High'
        }
    }
