"""
Terraform Manager for ZAP Cloud Plugin
Handles Terraform operations for infrastructure provisioning and teardown
"""

import subprocess
import json
import os
import shutil
from pathlib import Path
import tempfile


class TerraformManager:
    """Manages Terraform operations for cloud infrastructure"""
    
    def __init__(self, provider, work_dir, debug_callback=None):
        """
        Initialize Terraform manager
        
        :param provider: Cloud provider (aws, azure, gcp)
        :param work_dir: Working directory for Terraform operations
        :param debug_callback: Optional callback function for debug messages
        """
        self.provider = provider
        self.work_dir = Path(work_dir)
        self.debug = debug_callback or (lambda x: None)
        self.terraform_dir = None
        self.state_file = None
        self.last_stderr = None  # Store last error output for analysis
        
    def check_terraform_installed(self):
        """
        Check if Terraform is installed and accessible
        
        :return: True if installed, False otherwise
        """
        try:
            result = subprocess.run(
                ['terraform', 'version'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                version = result.stdout.split('\n')[0]
                self.debug(f"Terraform found: {version}")
                return True
            
            return False
            
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self.debug(f"Terraform not found: {e}")
            return False
    
    def prepare_workspace(self, terraform_module_dir, variables):
        """
        Prepare Terraform workspace with module files and variables
        
        :param terraform_module_dir: Source directory containing Terraform files
        :param variables: Dictionary of Terraform variables
        :return: Path to prepared workspace
        """
        try:
            # Create temporary working directory
            self.terraform_dir = self.work_dir / f"terraform_{self.provider}"
            self.terraform_dir.mkdir(parents=True, exist_ok=True)
            
            self.debug(f"Preparing Terraform workspace: {self.terraform_dir}")
            
            # Copy Terraform module files
            module_dir = Path(terraform_module_dir)
            for tf_file in module_dir.glob('*.tf'):
                dest = self.terraform_dir / tf_file.name
                shutil.copy2(tf_file, dest)
                self.debug(f"Copied {tf_file.name}")
            
            # Create terraform.tfvars file
            tfvars_path = self.terraform_dir / 'terraform.tfvars'
            with open(tfvars_path, 'w') as f:
                for key, value in variables.items():
                    if isinstance(value, str):
                        # Escape quotes and newlines in strings
                        value = value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                        f.write(f'{key} = "{value}"\n')
                    elif isinstance(value, bool):
                        f.write(f'{key} = {str(value).lower()}\n')
                    elif isinstance(value, (int, float)):
                        f.write(f'{key} = {value}\n')
                    elif isinstance(value, dict):
                        # Write dict as HCL map
                        f.write(f'{key} = {{\n')
                        for k, v in value.items():
                            if isinstance(v, str):
                                v = v.replace('\\', '\\\\').replace('"', '\\"')
                                f.write(f'  {k} = "{v}"\n')
                            else:
                                f.write(f'  {k} = {v}\n')
                        f.write('}\n')
            
            self.debug(f"Created terraform.tfvars")
            
            # Set state file location
            self.state_file = self.terraform_dir / 'terraform.tfstate'
            
            return self.terraform_dir
            
        except Exception as e:
            self.debug(f"Failed to prepare workspace: {e}")
            raise
    
    def init(self):
        """
        Initialize Terraform in the workspace
        
        :return: True if successful
        """
        try:
            self.debug("Running terraform init...")
            
            result = subprocess.run(
                ['terraform', 'init'],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                self.debug("Terraform init successful")
                return True
            else:
                self.debug(f"Terraform init failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.debug(f"Terraform init error: {e}")
            return False
    
    def plan(self):
        """
        Run terraform plan
        
        :return: True if successful
        """
        try:
            self.debug("Running terraform plan...")
            
            result = subprocess.run(
                ['terraform', 'plan', '-out=tfplan'],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                self.debug("Terraform plan successful")
                # Log plan output for debugging
                if result.stdout:
                    self.debug(f"Plan output:\n{result.stdout[:1000]}")
                return True
            else:
                self.debug(f"Terraform plan failed: {result.stderr}")
                return False
                
        except Exception as e:
            self.debug(f"Terraform plan error: {e}")
            return False
    
    def apply(self, timeout=600):
        """
        Apply Terraform configuration
        
        :param timeout: Maximum time to wait for apply
        :return: True if successful
        """
        try:
            self.debug("Running terraform apply...")
            
            result = subprocess.run(
                ['terraform', 'apply', '-auto-approve', 'tfplan'],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Store stderr for error analysis
            self.last_stderr = result.stderr
            
            if result.returncode == 0:
                self.debug("Terraform apply successful")
                if result.stdout:
                    self.debug(f"Apply output:\n{result.stdout[-500:]}")  # Last 500 chars
                return True
            else:
                self.debug(f"Terraform apply failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.debug(f"Terraform apply timed out after {timeout}s")
            self.last_stderr = f"Timeout after {timeout}s"
            return False
        except Exception as e:
            self.debug(f"Terraform apply error: {e}")
            self.last_stderr = str(e)
            return False
    
    def is_capacity_error(self):
        """
        Check if last failure was due to spot/preemptible capacity issues
        
        :return: True if capacity error detected
        """
        if not self.last_stderr:
            return False
        
        stderr_lower = self.last_stderr.lower()
        
        # AWS spot capacity errors
        aws_errors = [
            'insufficientinstancecapacity',
            'max spot instance count exceeded',
            'spot market capacity not available',
            'capacity-not-available',
            'spot-instance-count-exceeded',
            'spotmaxpricetoolow'
        ]
        
        # Azure spot capacity errors
        azure_errors = [
            'skunotavailable',
            'allocationfailed',
            'overconstrainedallocationrequest',
            'capacity not available',
            'spotvm quota',
            'lowpriorityvm quota'
        ]
        
        # GCP preemptible capacity errors
        gcp_errors = [
            'zone_resource_pool_exhausted',
            'quota exceeded',
            'insufficient resources',
            'preemptible_quota_exceeded',
            'resource_pool_exhausted'
        ]
        
        all_errors = aws_errors + azure_errors + gcp_errors
        return any(error in stderr_lower for error in all_errors)
    
    def get_outputs(self):
        """
        Get Terraform outputs
        
        :return: Dictionary of outputs
        """
        try:
            self.debug("Retrieving Terraform outputs...")
            
            result = subprocess.run(
                ['terraform', 'output', '-json'],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                outputs_raw = json.loads(result.stdout)
                
                # Extract values from Terraform output format
                outputs = {}
                for key, value in outputs_raw.items():
                    outputs[key] = value.get('value')
                
                self.debug(f"Outputs: {outputs}")
                return outputs
            else:
                self.debug(f"Failed to get outputs: {result.stderr}")
                return {}
                
        except Exception as e:
            self.debug(f"Error getting outputs: {e}")
            return {}
    
    def destroy(self, timeout=600):
        """
        Destroy Terraform-managed infrastructure
        
        :param timeout: Maximum time to wait for destroy
        :return: True if successful
        """
        try:
            self.debug("Running terraform destroy...")
            
            result = subprocess.run(
                ['terraform', 'destroy', '-auto-approve'],
                cwd=self.terraform_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                self.debug("Terraform destroy successful")
                return True
            else:
                self.debug(f"Terraform destroy failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.debug(f"Terraform destroy timed out after {timeout}s")
            return False
        except Exception as e:
            self.debug(f"Terraform destroy error: {e}")
            return False
    
    def cleanup_workspace(self):
        """
        Clean up Terraform workspace
        """
        try:
            if self.terraform_dir and self.terraform_dir.exists():
                self.debug(f"Cleaning up workspace: {self.terraform_dir}")
                shutil.rmtree(self.terraform_dir)
        except Exception as e:
            self.debug(f"Failed to cleanup workspace: {e}")
    
    def provision(self, terraform_module_dir, variables, timeout=600):
        """
        Complete provisioning workflow: prepare, init, plan, apply
        
        :param terraform_module_dir: Directory containing Terraform module
        :param variables: Terraform variables
        :param timeout: Timeout for apply operation
        :return: Tuple of (success, outputs)
        """
        try:
            # Check Terraform installation
            if not self.check_terraform_installed():
                raise RuntimeError("Terraform is not installed or not in PATH")
            
            # Prepare workspace
            self.prepare_workspace(terraform_module_dir, variables)
            
            # Initialize
            if not self.init():
                raise RuntimeError("Terraform init failed")
            
            # Plan
            if not self.plan():
                raise RuntimeError("Terraform plan failed")
            
            # Apply
            if not self.apply(timeout=timeout):
                raise RuntimeError("Terraform apply failed")
            
            # Get outputs
            outputs = self.get_outputs()
            
            return True, outputs
            
        except Exception as e:
            self.debug(f"Provisioning failed: {e}")
            return False, {}
    
    def teardown(self, timeout=600):
        """
        Complete teardown workflow: destroy, cleanup
        
        :param timeout: Timeout for destroy operation
        :return: True if successful
        """
        try:
            # Destroy infrastructure
            if not self.destroy(timeout=timeout):
                self.debug("Terraform destroy had errors, but continuing cleanup")
            
            # Cleanup workspace
            self.cleanup_workspace()
            
            return True
            
        except Exception as e:
            self.debug(f"Teardown failed: {e}")
            return False
