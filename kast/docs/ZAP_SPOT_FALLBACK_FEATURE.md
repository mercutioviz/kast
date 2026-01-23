# ZAP Cloud Spot Instance Fallback Feature

## Overview

The ZAP Cloud Plugin now includes automatic fallback from spot/preemptible instances to on-demand instances when spot capacity is unavailable. This feature ensures scan reliability while maximizing cost savings.

## How It Works

### Provisioning Flow

```
1. First Attempt: Spot/Preemptible Instance
   ├─ Configure Terraform with spot=true
   ├─ Run terraform init/plan/apply
   └─ If successful → Use spot instance ✓
   
2. If Spot Fails (Capacity Error Detected):
   ├─ Clean up failed spot attempt
   ├─ Configure Terraform with spot=false
   ├─ Run terraform init/plan/apply
   └─ If successful → Use on-demand instance ✓
   
3. If Both Fail:
   └─ Return error to user
```

### Error Detection

The system detects capacity errors by analyzing Terraform stderr output for provider-specific error messages:

**AWS Spot Errors:**
- `InsufficientInstanceCapacity`
- `Max spot instance count exceeded`
- `Spot market capacity not available`
- `SpotMaxPriceTooLow`

**Azure Spot Errors:**
- `SkuNotAvailable`
- `AllocationFailed`
- `OverconstrainedAllocationRequest`
- `SpotVM quota`

**GCP Preemptible Errors:**
- `ZONE_RESOURCE_POOL_EXHAUSTED`
- `Quota exceeded`
- `Preemptible_quota_exceeded`

## Configuration

### Cloud Provider Configs

All three cloud providers now support the `use_spot_instance` / `use_preemptible_instance` variable:

**AWS** (`kast/terraform/aws/variables.tf`):
```hcl
variable "use_spot_instance" {
  description = "Use spot instance (true) or on-demand (false)"
  type        = bool
  default     = true
}
```

**Azure** (`kast/terraform/azure/variables.tf`):
```hcl
variable "use_spot_instance" {
  description = "Use spot instance (true) or standard (false)"
  type        = bool
  default     = true
}
```

**GCP** (`kast/terraform/gcp/variables.tf`):
```hcl
variable "use_preemptible_instance" {
  description = "Use preemptible instance (true) or standard (false)"
  type        = bool
  default     = true
}
```

### Terraform Resources

Each provider's `main.tf` now includes conditional logic:

**AWS Example:**
```hcl
resource "aws_instance" "zap_instance" {
  # ... other configuration ...
  
  instance_market_options = var.use_spot_instance ? [{
    market_type = "spot"
    spot_options = {
      max_price = "0.05"
      spot_instance_type = "one-time"
    }
  }] : []
}
```

**Azure Example:**
```hcl
resource "azurerm_linux_virtual_machine" "zap_vm" {
  # ... other configuration ...
  
  priority        = var.use_spot_instance ? "Spot" : "Regular"
  eviction_policy = var.use_spot_instance ? "Deallocate" : null
  max_bid_price   = var.use_spot_instance ? var.spot_max_price : null
}
```

**GCP Example:**
```hcl
resource "google_compute_instance" "zap_instance" {
  # ... other configuration ...
  
  scheduling {
    preemptible                 = var.use_preemptible_instance
    automatic_restart           = false
    on_host_maintenance         = "TERMINATE"
    provisioning_model          = var.use_preemptible_instance ? "SPOT" : "STANDARD"
    instance_termination_action = var.use_preemptible_instance ? "DELETE" : null
  }
}
```

## Code Components

### 1. TerraformManager (`kast/scripts/terraform_manager.py`)

**New Attributes:**
- `last_stderr`: Stores stderr output from failed terraform operations

**New Methods:**
- `is_capacity_error()`: Analyzes stderr to detect spot capacity errors

```python
def is_capacity_error(self):
    """Check if last failure was due to spot/preemptible capacity issues"""
    if not self.last_stderr:
        return False
    
    stderr_lower = self.last_stderr.lower()
    
    # Check for AWS, Azure, GCP capacity errors
    aws_errors = ['insufficientinstancecapacity', ...]
    azure_errors = ['skunotavailable', ...]
    gcp_errors = ['zone_resource_pool_exhausted', ...]
    
    all_errors = aws_errors + azure_errors + gcp_errors
    return any(error in stderr_lower for error in all_errors)
```

### 2. CloudZapProvider (`kast/scripts/zap_providers.py`)

**Modified Methods:**
- `_prepare_terraform_variables(target_url, use_spot=True)`: Now accepts `use_spot` parameter

**New Methods:**
- `_provision_with_retry(target_url, output_dir, use_spot=True)`: Implements retry logic

```python
def _provision_with_retry(self, target_url, output_dir, use_spot=True):
    """Provision with automatic fallback from spot to on-demand"""
    
    # Attempt 1: Try spot instances
    if use_spot:
        tf_vars = self._prepare_terraform_variables(target_url, use_spot=True)
        # ... terraform workflow ...
        
        if terraform_manager.apply():
            return True, "spot", None
        
        # Check if capacity error
        if terraform_manager.is_capacity_error():
            # Clean up and retry with on-demand
            pass
        else:
            # Non-capacity error - don't retry
            return False, None, {"error": "..."}
    
    # Attempt 2: Try on-demand instances
    tf_vars = self._prepare_terraform_variables(target_url, use_spot=False)
    # ... terraform workflow ...
    
    if terraform_manager.apply():
        return True, "on-demand", None
    else:
        return False, None, {"error": "..."}
```

### 3. Terraform Outputs

All providers now include `instance_type` output:

```hcl
output "instance_type" {
  description = "Type of instance provisioned (spot/preemptible or on-demand/standard)"
  value       = var.use_spot_instance ? "spot" : "on-demand"
}
```

## User Experience

### Successful Spot Provision

```
Provisioning cloud infrastructure...
============================================================
ATTEMPT 1: Provisioning with spot/preemptible instances
============================================================
Using cloud provider: aws
Initializing Terraform...
Terraform init successful
Running terraform plan...
Terraform plan successful
Applying Terraform configuration (spot instances)...
✓ Spot instance provisioned successfully
Infrastructure provisioned - Instance IP: 54.123.45.67
```

### Spot Fallback to On-Demand

```
Provisioning cloud infrastructure...
============================================================
ATTEMPT 1: Provisioning with spot/preemptible instances
============================================================
Using cloud provider: aws
Initializing Terraform...
Terraform init successful
Running terraform plan...
Terraform plan successful
Applying Terraform configuration (spot instances)...
Terraform apply failed: InsufficientInstanceCapacity
⚠ Spot instance capacity unavailable, will retry with on-demand
Note: Cleanup after failed spot attempt

============================================================
ATTEMPT 2: Provisioning with on-demand instances
============================================================
Preparing new workspace...
Running terraform plan...
Terraform plan successful
Applying Terraform configuration (on-demand instances)...
✓ On-demand instance provisioned successfully
Infrastructure provisioned - Instance IP: 54.123.45.67
```

### Total Failure

```
Provisioning cloud infrastructure...
============================================================
ATTEMPT 1: Provisioning with spot/preemptible instances
============================================================
...
Terraform apply failed: InvalidParameterValue

ERROR: Terraform apply failed (non-capacity error)
```

## Cost Implications

### Spot vs On-Demand Pricing

**AWS** (us-east-1, t3.medium):
- On-Demand: $0.0416/hour
- Spot: $0.0125/hour (~70% savings)

**Azure** (East US, Standard_B2s):
- Regular: $0.0416/hour  
- Spot: $0.0042/hour (~90% savings)

**GCP** (us-central1, e2-medium):
- Standard: $0.0335/hour
- Preemptible: $0.0101/hour (~70% savings)

### Expected Behavior

With automatic fallback:
1. **Best case**: Spot available → 70-90% cost savings
2. **Fallback case**: Spot unavailable → Standard pricing, but scan proceeds
3. **Worst case**: Both fail → User informed, no infrastructure costs incurred

## Testing

### Test Scenarios

1. **Spot Success Path**
   - Verify spot instance provisions successfully
   - Check `instance_type` output = "spot"
   - Confirm ZAP container starts and scans work

2. **Spot-to-On-Demand Fallback**
   - Simulate spot capacity error
   - Verify automatic cleanup of failed attempt
   - Verify successful on-demand provisioning
   - Check `instance_type` output = "on-demand"

3. **Total Failure**
   - Simulate non-capacity error (e.g., invalid credentials)
   - Verify no retry attempt
   - Verify graceful error reporting

### Manual Testing Commands

```bash
# Test with AWS
python -m kast.main scan \
  --target https://example.com \
  --plugins zap \
  --set zap.mode=cloud \
  --set zap.cloud.cloud_provider=aws \
  --verbose

# Test with Azure
python -m kast.main scan \
  --target https://example.com \
  --plugins zap \
  --set zap.mode=cloud \
  --set zap.cloud.cloud_provider=azure \
  --verbose

# Test with GCP
python -m kast.main scan \
  --target https://example.com \
  --plugins zap \
  --set zap.mode=cloud \
  --set zap.cloud.cloud_provider=gcp \
  --verbose
```

## Troubleshooting

### Spot Capacity Always Unavailable

**Symptoms:**
- Always falls back to on-demand
- Spot instances never provision

**Solutions:**
1. Try different regions/zones
2. Try different instance types
3. Check spot pricing limits in Terraform variables
4. Review AWS/Azure/GCP service quotas

### Both Spot and On-Demand Fail

**Symptoms:**
- Both provision attempts fail
- Error: "Terraform apply failed"

**Common Causes:**
1. Invalid cloud credentials
2. Insufficient permissions (IAM/RBAC)
3. Service quotas exceeded
4. Network/VPC configuration issues
5. Invalid Terraform configuration

**Debugging Steps:**
```bash
# Check Terraform state
cd test_output/<scan_dir>/terraform_workspace_ondemand
terraform show

# Review Terraform logs
cat terraform.log

# Test cloud provider auth
aws sts get-caller-identity  # AWS
az account show              # Azure
gcloud auth list             # GCP
```

### Cleanup Issues

**Symptoms:**
- Resources not cleaned up after failed spot attempt
- Orphaned Terraform state

**Solutions:**
```bash
# Manual cleanup (if needed)
cd test_output/<scan_dir>/terraform_workspace
terraform destroy -auto-approve

# Check for running instances
aws ec2 describe-instances --filters "Name=tag:project,Values=kast"
az vm list --query "[?tags.project=='kast']"
gcloud compute instances list --filter="labels.project=kast"
```

## Future Enhancements

1. **Configurable Retry Behavior**
   - Allow users to disable auto-fallback
   - Support multiple retry attempts with different regions

2. **Cost Tracking**
   - Log actual costs incurred
   - Report savings from spot usage

3. **Intelligent Region Selection**
   - Automatically try different regions on capacity failures
   - Use historical data to prefer regions with good spot availability

4. **Mixed Fleet Support**
   - Try multiple instance types
   - Use smallest available instance that meets requirements

## References

- AWS Spot Instances: https://aws.amazon.com/ec2/spot/
- Azure Spot VMs: https://azure.microsoft.com/en-us/products/virtual-machines/spot/
- GCP Preemptible VMs: https://cloud.google.com/compute/docs/instances/preemptible

## Changelog

### Version 1.0 (January 2026)
- Initial implementation of spot-to-on-demand fallback
- Support for AWS, Azure, and GCP
- Automatic capacity error detection
- Graceful degradation with user notification
