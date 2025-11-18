#!/usr/bin/env python3
"""
Simple test script to verify --report-only target extraction from kast_info.json
"""

import json
import tempfile
import shutil
from pathlib import Path

def test_kast_info_extraction():
    """Test that we can extract target from kast_info.json"""
    
    # Create a temporary directory with a sample kast_info.json
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        # Create sample kast_info.json
        kast_info = {
            "kast_version": "2.3.0",
            "start_timestamp": "2025-11-11T16:19:25.885302",
            "end_timestamp": "2025-11-11T16:21:15.113785",
            "duration_seconds": 109.23,
            "cli_arguments": {
                "target": "waas.az.hackazon.lkscd.com",
                "mode": "passive",
                "parallel": False,
                "verbose": False,
                "output_dir": "/home/kali/kast_results/waas.az.hackazon.lkscd.com-20251111-161925",
                "run_only": "mozilla_observatory,subfinder,wafw00f,whatweb,katana",
                "log_dir": "/var/log/kast/"
            }
        }
        
        kast_info_path = temp_dir / "kast_info.json"
        with open(kast_info_path, 'w') as f:
            json.dump(kast_info, f, indent=2)
        
        print(f"✓ Created test kast_info.json at: {kast_info_path}")
        
        # Read it back and verify
        with open(kast_info_path, 'r') as f:
            loaded_info = json.load(f)
        
        if 'cli_arguments' in loaded_info and 'target' in loaded_info['cli_arguments']:
            target = loaded_info['cli_arguments']['target']
            print(f"✓ Successfully extracted target: {target}")
            print(f"\nTest directory: {temp_dir}")
            print(f"\nYou can test with:")
            print(f"  python main.py --report-only {temp_dir}")
            return True
        else:
            print("✗ Failed to extract target from kast_info.json")
            return False
            
    except Exception as e:
        print(f"✗ Test failed with error: {e}")
        return False
    finally:
        # Clean up
        print(f"\nCleaning up test directory: {temp_dir}")
        shutil.rmtree(temp_dir)

if __name__ == "__main__":
    print("Testing kast_info.json target extraction...\n")
    success = test_kast_info_extraction()
    exit(0 if success else 1)
