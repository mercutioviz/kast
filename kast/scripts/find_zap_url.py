#!/usr/bin/env python3
"""
Simple utility to find and print ZAP API URL from infrastructure state

Usage:
    python3 kast/scripts/find_zap_url.py
    
Output:
    http://34.220.11.146:8080
    
Exit codes:
    0 - URL found and printed
    1 - No infrastructure found
"""

import sys
from pathlib import Path


def find_latest_zap_infrastructure():
    """
    Scan for most recent ZAP infrastructure state file
    
    Returns:
        tuple: (zap_url, api_key, timestamp) or (None, None, None) if not found
    """
    # Directories to search
    search_dirs = [
        Path(__file__).parent.parent.parent / "test_output",
        Path(__file__).parent.parent.parent / "output"
    ]
    
    state_files = []
    
    # Find all infrastructure_state.txt files
    for search_dir in search_dirs:
        if search_dir.exists():
            for state_file in search_dir.rglob("infrastructure_state.txt"):
                state_files.append(state_file)
    
    if not state_files:
        return None, None, None
    
    # Parse state files and find most recent
    latest_state = None
    latest_timestamp = None
    
    for state_file in state_files:
        try:
            with open(state_file, 'r') as f:
                content = f.read()
            
            # Parse the state file
            zap_url = None
            timestamp = None
            api_key = None
            
            for line in content.split('\n'):
                if line.startswith('Timestamp:'):
                    timestamp = line.split(':', 1)[1].strip()
                elif 'zap_api_url:' in line:
                    zap_url = line.split(':', 1)[1].strip()
                    # Handle format "zap_api_url: http://..."
                    if zap_url.startswith('http'):
                        pass
                    else:
                        # Try to extract from full line
                        if 'http' in line:
                            zap_url = 'http' + line.split('http')[1].strip()
            
            # Extract API key from config (default to kast01)
            api_key = "kast01"
            
            if zap_url and timestamp:
                # Compare timestamps to find latest
                if latest_timestamp is None or timestamp > latest_timestamp:
                    latest_timestamp = timestamp
                    latest_state = (zap_url, api_key, timestamp)
        
        except Exception:
            continue
    
    return latest_state if latest_state else (None, None, None)


def main():
    zap_url, api_key, timestamp = find_latest_zap_infrastructure()
    
    if zap_url:
        print(zap_url)
        return 0
    else:
        print("No ZAP infrastructure found", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
