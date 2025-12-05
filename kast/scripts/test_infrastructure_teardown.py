#!/usr/bin/env python3
"""
Test script for tearing down cloud infrastructure
Destroys infrastructure created by test_infrastructure_provision.py

Usage:
    python test_infrastructure_teardown.py <state_info_file>
    python test_infrastructure_teardown.py /path/to/infrastructure_state.txt
"""

import sys
import os
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.terraform_manager import TerraformManager


def print_header(message):
    """Print formatted header"""
    print("\n" + "=" * 70)
    print(f"  {message}")
    print("=" * 70 + "\n")


def print_step(step_num, message):
    """Print formatted step"""
    print(f"\n[Step {step_num}] {message}")
    print("-" * 70)


def print_success(message):
    """Print success message"""
    print(f"\n✓ SUCCESS: {message}\n")


def print_error(message):
    """Print error message"""
    print(f"\n✗ ERROR: {message}\n")


def print_warning(message):
    """Print warning message"""
    print(f"\n⚠ WARNING: {message}\n")


def print_info(message):
    """Print info message"""
    print(f"  → {message}")


def load_state_info(state_info_path):
    """
    Load infrastructure state information from file
    
    :param state_info_path: Path to state info file
    :return: Dictionary with state information
    """
    state_info = {}
    
    try:
        with open(state_info_path, 'r') as f:
            for line in f:
                line = line.strip()
                if ':' in line and not line.startswith('Outputs:'):
                    key, value = line.split(':', 1)
                    state_info[key.strip()] = value.strip()
        
        return state_info
        
    except Exception as e:
        print_error(f"Failed to load state info: {e}")
        return None


def confirm_teardown(provider, terraform_dir):
    """
    Ask user to confirm teardown operation
    
    :param provider: Cloud provider
    :param terraform_dir: Terraform directory
    :return: True if confirmed
    """
    print_warning("You are about to destroy cloud infrastructure!")
    print_info(f"Provider: {provider}")
    print_info(f"Terraform Directory: {terraform_dir}")
    print()
    
    response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
    
    return response in ['yes', 'y']


def teardown_infrastructure(state_info_path):
    """
    Teardown cloud infrastructure
    
    :param state_info_path: Path to state info file
    :return: True if successful
    """
    print_header("Infrastructure Teardown")
    
    try:
        # Step 1: Load state information
        print_step(1, "Loading infrastructure state")
        state_info = load_state_info(state_info_path)
        
        if not state_info:
            print_error("Failed to load state information")
            return False
        
        provider = state_info.get('Provider')
        terraform_dir = state_info.get('Terraform Directory')
        
        if not provider or not terraform_dir:
            print_error("Invalid state information - missing provider or terraform directory")
            return False
        
        print_info(f"Provider: {provider}")
        print_info(f"Terraform Directory: {terraform_dir}")
        print_success("State information loaded")
        
        # Step 2: Verify Terraform directory exists
        print_step(2, "Verifying Terraform directory")
        terraform_dir_path = Path(terraform_dir)
        
        if not terraform_dir_path.exists():
            print_error(f"Terraform directory not found: {terraform_dir}")
            print_info("Infrastructure may have already been destroyed")
            return False
        
        # Check for state file
        state_file = terraform_dir_path / "terraform.tfstate"
        if not state_file.exists():
            print_warning("No terraform.tfstate found - infrastructure may not exist")
            
        print_success("Terraform directory found")
        
        # Step 3: Confirm teardown
        print_step(3, "Confirmation")
        if not confirm_teardown(provider, terraform_dir):
            print_warning("Teardown cancelled by user")
            return False
        
        print_success("Teardown confirmed")
        
        # Step 4: Initialize Terraform manager
        print_step(4, "Initializing Terraform manager")
        
        def debug_callback(msg):
            print_info(msg)
        
        # Use parent of terraform directory as work_dir
        work_dir = terraform_dir_path.parent
        tf_manager = TerraformManager(provider, work_dir, debug_callback)
        tf_manager.terraform_dir = terraform_dir_path
        tf_manager.state_file = state_file
        
        print_success("Terraform manager initialized")
        
        # Step 5: Destroy infrastructure
        print_step(5, "Destroying infrastructure (this may take several minutes)")
        print_info("Running: terraform destroy")
        
        success = tf_manager.destroy(timeout=900)
        
        if not success:
            print_error("Infrastructure destruction failed")
            print_warning("You may need to manually destroy resources in the cloud console")
            return False
        
        print_success("Infrastructure destroyed successfully")
        
        # Step 6: Cleanup workspace
        print_step(6, "Cleaning up workspace")
        tf_manager.cleanup_workspace()
        print_success("Workspace cleaned up")
        
        # Step 7: Remove state info file
        print_step(7, "Removing state info file")
        try:
            state_info_file = Path(state_info_path)
            if state_info_file.exists():
                state_info_file.unlink()
                print_info(f"Removed: {state_info_path}")
        except Exception as e:
            print_warning(f"Could not remove state info file: {e}")
        
        # Success summary
        print_header("Teardown Complete")
        print_success(f"{provider.upper()} infrastructure has been destroyed")
        print_info("All cloud resources have been removed")
        print("\n" + "=" * 70 + "\n")
        
        return True
        
    except KeyboardInterrupt:
        print_error("Teardown interrupted by user")
        print_warning("Infrastructure may still be running - check cloud console")
        return False
    except Exception as e:
        print_error(f"Teardown failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def find_state_files():
    """
    Find all infrastructure state files in test_output directory
    
    :return: List of state file paths
    """
    test_output_dir = Path(__file__).parent.parent.parent / "test_output"
    
    if not test_output_dir.exists():
        return []
    
    state_files = []
    for state_file in test_output_dir.rglob("infrastructure_state.txt"):
        state_files.append(state_file)
    
    return state_files


def interactive_teardown():
    """
    Interactive mode - let user select from available state files
    """
    print_header("Interactive Teardown")
    
    state_files = find_state_files()
    
    if not state_files:
        print_info("No infrastructure state files found")
        print_info("Nothing to tear down")
        return False
    
    print_info(f"Found {len(state_files)} infrastructure state(s):\n")
    
    for i, state_file in enumerate(state_files, 1):
        # Load and display info
        state_info = load_state_info(state_file)
        if state_info:
            provider = state_info.get('Provider', 'unknown')
            timestamp = state_info.get('Timestamp', 'unknown')
            print(f"  [{i}] {provider.upper()} - {timestamp}")
            print(f"      {state_file}")
            print()
    
    print(f"  [0] Tear down ALL infrastructure")
    print(f"  [q] Quit\n")
    
    choice = input("Select infrastructure to tear down: ").strip().lower()
    
    if choice == 'q':
        print_info("Cancelled")
        return False
    
    try:
        if choice == '0':
            # Tear down all
            print_info(f"Tearing down all {len(state_files)} infrastructure(s)...")
            success_count = 0
            for state_file in state_files:
                if teardown_infrastructure(state_file):
                    success_count += 1
            
            print_header(f"Batch Teardown Complete: {success_count}/{len(state_files)} successful")
            return success_count == len(state_files)
        else:
            # Tear down selected
            idx = int(choice) - 1
            if 0 <= idx < len(state_files):
                return teardown_infrastructure(state_files[idx])
            else:
                print_error("Invalid selection")
                return False
    except ValueError:
        print_error("Invalid input")
        return False


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Teardown cloud infrastructure created by test_infrastructure_provision.py',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Tear down specific infrastructure
  python test_infrastructure_teardown.py /path/to/infrastructure_state.txt
  
  # Interactive mode (select from available infrastructure)
  python test_infrastructure_teardown.py
  
  # Tear down all test infrastructure
  python test_infrastructure_teardown.py --all

Note: This will permanently destroy cloud resources. Use with caution.
        '''
    )
    parser.add_argument(
        'state_file',
        nargs='?',
        help='Path to infrastructure_state.txt file (optional for interactive mode)'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Tear down all test infrastructure without prompting'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    args = parser.parse_args()
    
    if args.all:
        # Tear down all infrastructure
        state_files = find_state_files()
        if not state_files:
            print_info("No infrastructure found to tear down")
            sys.exit(0)
        
        print_info(f"Found {len(state_files)} infrastructure(s) to tear down")
        
        if not args.force:
            response = input(f"Tear down all {len(state_files)} infrastructure(s)? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print_info("Cancelled")
                sys.exit(0)
        
        success_count = 0
        for state_file in state_files:
            # Skip confirmation for batch mode
            if teardown_infrastructure(state_file):
                success_count += 1
        
        print_header(f"Batch Teardown Complete: {success_count}/{len(state_files)} successful")
        sys.exit(0 if success_count == len(state_files) else 1)
        
    elif args.state_file:
        # Tear down specific infrastructure
        state_file_path = Path(args.state_file)
        
        if not state_file_path.exists():
            print_error(f"State file not found: {args.state_file}")
            sys.exit(1)
        
        success = teardown_infrastructure(state_file_path)
        sys.exit(0 if success else 1)
        
    else:
        # Interactive mode
        success = interactive_teardown()
        sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
