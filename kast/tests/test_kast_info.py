#!/usr/bin/env python3
"""
Simple test script to verify kast_info.json generation
"""

import subprocess
import json
import sys
from pathlib import Path
import time

def test_kast_info_generation():
    """Test that kast_info.json is created with correct structure"""
    
    print("Testing kast_info.json generation...")
    
    # Run kast with dry-run to verify it doesn't create the file
    print("\n1. Testing --dry-run mode (should NOT create kast_info.json)...")
    result = subprocess.run(
        ["python3", "main.py", "-t", "example.com", "--dry-run"],
        capture_output=True,
        text=True
    )
    
    # Check that no kast_info.json was created in dry-run
    home = Path.home()
    kast_results = home / "kast_results"
    if kast_results.exists():
        for result_dir in kast_results.glob("example.com-*"):
            info_file = result_dir / "kast_info.json"
            if info_file.exists():
                print("   ❌ FAIL: kast_info.json should not be created in dry-run mode")
                return False
    print("   ✓ PASS: kast_info.json not created in dry-run mode")
    
    # Run kast normally (this will actually execute)
    print("\n2. Testing normal execution (should create kast_info.json)...")
    print("   Note: This will run actual plugins if available...")
    
    result = subprocess.run(
        ["python3", "main.py", "-t", "example.com", "-m", "passive"],
        capture_output=True,
        text=True,
        timeout=60
    )
    
    # Find the most recent output directory
    if not kast_results.exists():
        print("   ❌ FAIL: No kast_results directory found")
        return False
    
    result_dirs = sorted(kast_results.glob("example.com-*"), key=lambda x: x.stat().st_mtime, reverse=True)
    if not result_dirs:
        print("   ❌ FAIL: No result directory found")
        return False
    
    latest_dir = result_dirs[0]
    info_file = latest_dir / "kast_info.json"
    
    if not info_file.exists():
        print(f"   ❌ FAIL: kast_info.json not found in {latest_dir}")
        return False
    
    print(f"   ✓ Found kast_info.json in {latest_dir}")
    
    # Verify JSON structure
    print("\n3. Verifying JSON structure...")
    try:
        with open(info_file, 'r') as f:
            kast_info = json.load(f)
        
        # Check required fields
        required_fields = [
            "kast_version",
            "start_timestamp",
            "end_timestamp",
            "duration_seconds",
            "cli_arguments",
            "plugins"
        ]
        
        for field in required_fields:
            if field not in kast_info:
                print(f"   ❌ FAIL: Missing required field: {field}")
                return False
            print(f"   ✓ Found field: {field}")
        
        # Check CLI arguments structure
        cli_args = kast_info["cli_arguments"]
        required_cli_fields = ["target", "mode", "parallel", "verbose", "output_dir"]
        for field in required_cli_fields:
            if field not in cli_args:
                print(f"   ❌ FAIL: Missing CLI argument field: {field}")
                return False
        
        print(f"   ✓ CLI arguments structure valid")
        
        # Check plugins structure
        plugins = kast_info["plugins"]
        if not isinstance(plugins, list):
            print("   ❌ FAIL: plugins should be a list")
            return False
        
        print(f"   ✓ Found {len(plugins)} plugin timing entries")
        
        # Verify plugin timing structure
        if plugins:
            plugin = plugins[0]
            required_plugin_fields = ["plugin_name", "start_timestamp", "end_timestamp", "duration_seconds", "status"]
            for field in required_plugin_fields:
                if field not in plugin:
                    print(f"   ❌ FAIL: Missing plugin field: {field}")
                    return False
            print(f"   ✓ Plugin timing structure valid")
        
        # Display the content
        print("\n4. Sample kast_info.json content:")
        print(json.dumps(kast_info, indent=2))
        
        print("\n✅ ALL TESTS PASSED!")
        return True
        
    except json.JSONDecodeError as e:
        print(f"   ❌ FAIL: Invalid JSON: {e}")
        return False
    except Exception as e:
        print(f"   ❌ FAIL: Error reading file: {e}")
        return False

if __name__ == "__main__":
    try:
        success = test_kast_info_generation()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
