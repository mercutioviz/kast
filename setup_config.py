#!/usr/bin/env python3

import os
import sys
import yaml
from pathlib import Path

def main():
    """Set up KAST configuration"""
    print("KAST Configuration Setup")
    print("=======================")
    print("This script will help you set up your KAST configuration.")
    print("The configuration will be saved to ~/.config/kast/config.yaml")
    print()
    
    # Load default configuration
    default_config_path = os.path.join(os.path.dirname(__file__), "src", "config", "default_config.yaml")
    
    try:
        with open(default_config_path, 'r') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading default configuration: {e}")
        sys.exit(1)
    
    # Get API keys
    print("API Keys:")
    print("---------")
    print("Enter your API keys for the following services (leave empty to skip):")
    
    securityheaders_key = input("SecurityHeaders.com API Key: ").strip()
    if securityheaders_key:
        config['api_keys']['securityheaders'] = securityheaders_key
    
    ssllabs_key = input("SSL Labs API Key (if you have one): ").strip()
    if ssllabs_key:
        config['api_keys']['ssllabs'] = ssllabs_key
    
    # Get default output directory
    print("\nOutput Settings:")
    print("--------------")
    default_dir = input("Default output directory (leave empty for default): ").strip()
    if default_dir:
        config['output']['default_directory'] = default_dir
    
    # Save configuration
    user_config_path = os.path.expanduser("~/.config/kast/config.yaml")
    os.makedirs(os.path.dirname(user_config_path), exist_ok=True)
    
    try:
        with open(user_config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        print(f"\nConfiguration saved to {user_config_path}")
    except Exception as e:
        print(f"Error saving configuration: {e}")
        sys.exit(1)
    
    print("\nSetup complete!")
    print("You can now run KAST with your configuration.")

if __name__ == "__main__":
    main()
