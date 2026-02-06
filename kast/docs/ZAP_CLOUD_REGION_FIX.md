# ZAP Cloud Region Configuration Fix

## Issue Summary

CLI overrides for ZAP cloud configuration (specifically `--set zap.cloud.region=us-west-1`) were not being honored. The region would default to `us-east-1` regardless of the CLI argument.

## Root Cause

Two bugs were working together:

### Bug #1: Missing Overrideable Parameters
**File:** `kast/plugins/zap_plugin.py`
**Location:** `_apply_cli_overrides()` method

The hardcoded list of `overrideable_params` was missing all cloud provider-specific settings. It only included:
- `cloud.cloud_provider`
- `cloud.use_automation_framework`

But was missing:
- Generic cloud parameters: `cloud.region`, `cloud.instance_type`, `cloud.spot_max_price`, etc.
- AWS-specific: `cloud.aws.*`
- Azure-specific: `cloud.azure.*`
- GCP-specific: `cloud.gcp.*`

### Bug #2: Inconsistent Config Path Resolution
**File:** `kast/scripts/zap_providers.py`
**Location:** `_prepare_terraform_variables()` method

The config resolution logic had issues:
```python
aws_config = self.config.get('aws', {})  # Wrong path
variables.update({
    'region': cloud_config.get('region', 'us-east-1'),  # Only checked one path
})
```

This didn't properly check:
1. CLI overrides at `cloud.region` (generic)
2. Provider-specific YAML at `cloud.aws.region`

## Solution Implemented

### Fix #1: Expanded Overrideable Parameters List
Added all cloud configuration parameters to the overrideable list in `zap_plugin.py`:

```python
# Generic cloud parameters (used by all providers)
'cloud.region',
'cloud.instance_type',
'cloud.spot_max_price',
'cloud.allowed_cidrs',
'cloud.auto_terminate',
# AWS-specific parameters
'cloud.aws.region',
'cloud.aws.instance_type',
'cloud.aws.ami_id',
'cloud.aws.spot_max_price',
# Azure-specific parameters
'cloud.azure.region',
'cloud.azure.vm_size',
# ... etc
```

### Fix #2: Proper Config Resolution with Fallback Logic
Implemented a proper resolution order in `zap_providers.py`:

```python
# Region: CLI generic > CLI aws-specific > YAML aws-specific > default
region = cloud_config.get('region') or aws_config.get('region', 'us-east-1')
```

Resolution order for each parameter:
1. CLI override at `cloud.{param}` (generic, applies to all providers)
2. CLI override at `cloud.{provider}.{param}` (provider-specific)
3. YAML value at `cloud.{provider}.{param}` (provider-specific)
4. Hardcoded default

### Fix #3: Comprehensive Debug Logging
Added detailed debug logging to show:
- Config resolution steps for each parameter
- Source of each value (CLI generic, CLI provider-specific, YAML, or default)
- Final values being passed to Terraform

## Testing Recommendations

### Test 1: CLI Generic Override
```bash
kast -t example.com \
  --set zap.execution_mode=cloud \
  --set zap.cloud.provider=aws \
  --set zap.cloud.region=us-west-1 \
  --run-only zap -v
```

**Expected Output:**
```
[DEBUG] [zap]: AWS region resolution:
[DEBUG] [zap]:   cloud.region (CLI generic): us-west-1
[DEBUG] [zap]:   cloud.aws.region (YAML): None
[DEBUG] [zap]:   → Final value: us-west-1
```

### Test 2: Provider-Specific CLI Override
```bash
kast -t example.com \
  --set zap.execution_mode=cloud \
  --set zap.cloud.provider=aws \
  --set zap.cloud.aws.region=us-west-2 \
  --run-only zap -v
```

**Expected Output:**
```
[DEBUG] [zap]: AWS region resolution:
[DEBUG] [zap]:   cloud.region (CLI generic): None
[DEBUG] [zap]:   cloud.aws.region (YAML): us-west-2
[DEBUG] [zap]:   → Final value: us-west-2
```

### Test 3: Multiple Parameters
```bash
kast -t example.com \
  --set zap.execution_mode=cloud \
  --set zap.cloud.provider=aws \
  --set zap.cloud.region=eu-west-1 \
  --set zap.cloud.instance_type=t3.large \
  --set zap.cloud.spot_max_price=0.15 \
  --run-only zap -v
```

**Expected Output:**
```
[DEBUG] [zap]: AWS region resolution:
[DEBUG] [zap]:   → Final value: eu-west-1
[DEBUG] [zap]: AWS instance_type resolution:
[DEBUG] [zap]:   → Final value: t3.large
[DEBUG] [zap]: AWS spot_max_price: 0.15
```

### Test 4: Verify Terraform Variables
Check the generated `terraform.tfvars` file in the workspace:

```bash
# After provisioning starts, check:
cat <output_dir>/terraform_workspace/terraform_aws/terraform.tfvars
```

Should contain:
```hcl
region = "us-west-1"
instance_type = "t3.large"
spot_max_price = "0.15"
```

## Debug Log Analysis

The new debug logging shows the complete resolution chain. Example from a successful run:

```
[DEBUG] [zap]: === Preparing Terraform Variables ===
[DEBUG] [zap]: Cloud provider: aws
[DEBUG] [zap]: Use spot/preemptible: true
[DEBUG] [zap]: AWS region resolution:
[DEBUG] [zap]:   cloud.region (CLI generic): us-west-1
[DEBUG] [zap]:   cloud.aws.region (YAML): us-east-1
[DEBUG] [zap]:   → Final value: us-west-1
[DEBUG] [zap]: AWS instance_type resolution:
[DEBUG] [zap]:   cloud.instance_type (CLI): t3.medium
[DEBUG] [zap]:   cloud.aws.instance_type (YAML): None
[DEBUG] [zap]:   → Final value: t3.medium
[DEBUG] [zap]: === Terraform Variables Prepared ===
[DEBUG] [zap]: Final variables (non-sensitive): {'ssh_public_key': '...', 'target_url': '...', 'region': 'us-west-1', 'instance_type': 't3.medium', ...}
```

## Files Modified

1. `kast/plugins/zap_plugin.py`
   - Expanded `overrideable_params` list to include all cloud parameters
   - Added support for generic cloud parameters and provider-specific parameters

2. `kast/scripts/zap_providers.py`
   - Fixed `_prepare_terraform_variables()` method
   - Implemented proper config resolution with fallback logic
   - Added comprehensive debug logging showing resolution steps

## Backward Compatibility

This fix maintains backward compatibility:
- YAML-only configurations continue to work
- Provider-specific YAML settings are still respected
- CLI overrides now work as expected and take precedence
- No breaking changes to existing configurations

## Future Enhancements

Consider adding:
1. Config validation to catch conflicts between generic and provider-specific settings
2. Warning messages when provider-specific settings are ignored
3. Support for environment variable overrides (e.g., `KAST_ZAP_CLOUD_REGION`)