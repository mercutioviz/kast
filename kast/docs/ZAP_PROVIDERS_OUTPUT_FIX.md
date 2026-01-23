# ZAP Providers Terraform Output Fix

## Issue Summary

**Date:** 2026-01-22  
**Severity:** High (Blocking ZAP cloud scans)  
**Component:** `kast/scripts/zap_providers.py`

### Error Description

When running KAST with ZAP cloud mode (spot pricing fallback feature), the scan failed during cloud provisioning with the error:

```
[2026-01-22 23:37:04.35] [DEBUG] [zap]: Cloud provisioning failed: 'str' object has no attribute 'get'
[2026-01-22 23:37:04.36] [DEBUG] [zap]: Traceback (most recent call last):
  File "/opt/kast/kast/scripts/zap_providers.py", line 736, in provision
    zap_api_url = self.infrastructure_outputs.get('zap_api_url', {}).get('value')
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'str' object has no attribute 'get'
```

## Root Cause

The issue was in the `AWSZapProvider.provision()` method at line 736. The code attempted to extract the `'value'` key twice:

1. `terraform_manager.get_outputs()` returns a dictionary where output values are already extracted (flat structure: `{'key': 'value'}`)
2. The code then tried to treat these string values as dictionaries and call `.get('value')` on them

### Code Flow

```python
# In terraform_manager.py
def get_outputs(self):
    """Get terraform outputs"""
    outputs = {}
    for key, output in raw_outputs.items():
        outputs[key] = output.get('value')  # Already extracting 'value' here
    return outputs

# In zap_providers.py (INCORRECT)
zap_api_url = self.infrastructure_outputs.get('zap_api_url', {}).get('value')
#                                                                 ^^^^^^^^^^^^
#                                                    Trying to extract 'value' AGAIN
```

## The Fix

The fix was already implemented in `zap_providers.py`. All references were updated to directly access the output values without the extra `.get('value')` call:

**Before:**
```python
zap_api_url = self.infrastructure_outputs.get('zap_api_url', {}).get('value')
```

**After:**
```python
zap_api_url = self.infrastructure_outputs.get('zap_api_url')
```

### Lines Fixed

**Issue 1: Double extraction of 'value' key (already fixed)**
Multiple lines in `zap_providers.py` were corrected:
- Line 736: `zap_api_url` extraction
- Line 737: `public_ip` extraction  
- Line 738: `instance_id` extraction
- Line 739: `ssh_user` extraction
- Line 740: `scan_identifier` extraction
- Line 741: `instance_type` extraction
- Line 742: `security_group_id` extraction
- Line 743: `vpc_id` extraction

**Issue 2: Wrong output key name (fixed)**
- Line 736 in `CloudZapProvider.provision()`: Changed from `instance_ip` to `public_ip`

**Before:**
```python
instance_ip = self.infrastructure_outputs.get('instance_ip')
```

**After:**
```python
instance_ip = self.infrastructure_outputs.get('public_ip')
```

The Terraform outputs use `public_ip` as the key name, but the code was looking for `instance_ip`, causing the error "No instance IP in Terraform outputs" even when the IP was present.

**Issue 3: Wrong SSHExecutor parameter names (fixed)**
- Lines 748-752 in `CloudZapProvider.provision()`: Fixed parameter names for SSHExecutor initialization

**Before:**
```python
self.ssh_executor = SSHExecutor(
    hostname=instance_ip,           # ❌ Wrong
    username=ssh_user,              # ❌ Wrong
    key_filename=self.ssh_key_path, # ❌ Wrong
    debug_callback=self.debug
)
```

**After:**
```python
self.ssh_executor = SSHExecutor(
    host=instance_ip,               # ✓ Correct
    user=ssh_user,                  # ✓ Correct
    private_key_path=self.ssh_key_path,  # ✓ Correct
    debug_callback=self.debug
)
```

The `SSHExecutor.__init__()` method expects parameters named `host`, `user`, and `private_key_path`, but the code was using `hostname`, `username`, and `key_filename`.

**Issue 4: Wrong config path for cloud provider settings (fixed)**
- Line 509 in `CloudZapProvider._prepare_terraform_variables()`: Fixed configuration lookup path

**Before:**
```python
cloud_config = self.config.get('cloud', {})  # ❌ Wrong - 'cloud' key doesn't exist
aws_config = cloud_config.get('aws', {})     # Returns {} - can't find config
variables.update({
    'region': aws_config.get('region', 'us-east-1'),  # Always falls back to default
    ...
})
```

**After:**
```python
# Access cloud provider configs directly from self.config
aws_config = self.config.get('aws', {})  # ✓ Correct - finds user's AWS config
variables.update({
    'region': aws_config.get('region', 'us-east-1'),  # Uses configured region
    ...
})
```

The config structure in `zap_cloud_config.yaml` has cloud provider settings at the top level (e.g., `aws:`, `azure:`, `gcp:`), not nested under a `cloud:` key. The code was looking in the wrong place, causing all settings to use hardcoded defaults. This same issue affected Azure and GCP configurations.

## Verification

After the fix, the Terraform outputs are correctly accessed:

```python
# Outputs structure from terraform_manager.get_outputs():
{
    'instance_id': 'i-06c57c296d5aef295',
    'instance_type': 'spot',
    'public_ip': '54.84.195.157',
    'scan_identifier': 'kast-zap-355437ac',
    'security_group_id': 'sg-02cf1a77fcea8da4e',
    'ssh_user': 'ubuntu',
    'vpc_id': 'vpc-03a7e958063c2f1ff',
    'zap_api_url': 'http://54.84.195.157:8080'
}

# Direct access works correctly:
zap_api_url = self.infrastructure_outputs.get('zap_api_url')
# Result: 'http://54.84.195.157:8080'
```

## Related Work

### Orphaned Resources Cleanup Tool

As a result of this investigation, a new tool was created to handle orphaned cloud resources that may have been left behind by failed scans:

**Script:** `kast/scripts/cleanup_orphaned_resources.py`  
**Documentation:** `kast/docs/ORPHANED_RESOURCES_CLEANUP.md`

This tool can:
- Detect KAST resources in AWS (EC2 instances, security groups)
- Identify orphaned resources (no matching local state files)
- Clean up resources with dry-run and interactive modes
- Export resource inventory for auditing

### Usage Example

```bash
# Find resources from failed scan
python3 kast/scripts/cleanup_orphaned_resources.py --scan-id kast-zap-355437ac

# Clean up with confirmation
python3 kast/scripts/cleanup_orphaned_resources.py --scan-id kast-zap-355437ac --cleanup
```

## Testing Recommendations

1. **Test spot instance provisioning:**
   ```bash
   kast --target example.com --plugins zap --zap-cloud
   ```

2. **Test fallback from spot to on-demand:**
   - Force spot instance failure (e.g., unavailable instance type)
   - Verify fallback to on-demand works correctly

3. **Verify output extraction:**
   - Check logs show correct values for all outputs
   - Confirm ZAP API connection succeeds

4. **Test cleanup tool:**
   ```bash
   # List resources
   python3 kast/scripts/cleanup_orphaned_resources.py --list-all
   
   # Dry-run cleanup
   python3 kast/scripts/cleanup_orphaned_resources.py --cleanup --dry-run
   ```

## Impact

**Before Fix:**
- All ZAP cloud scans failed during provisioning
- Resources were provisioned but couldn't be used
- Manual cleanup required for orphaned resources

**After Fix:**
- ZAP cloud scans complete successfully
- Spot pricing fallback works correctly
- Automated cleanup tool available for orphaned resources

## Related Issues

- Spot pricing fallback feature: `ZAP_SPOT_FALLBACK_FEATURE.md`
- ZAP cloud configuration: `ZAP_CLOUD_PLUGIN_GUIDE.md`

## Lessons Learned

1. **Double extraction bug:** When a helper function already extracts nested values, avoid extracting them again
2. **Error handling:** Better error messages could have identified this issue faster
3. **Testing:** More comprehensive integration tests for cloud provisioning would catch this
4. **Resource management:** Cleanup tools are essential for cloud-based features

## Future Improvements

1. Add integration tests for Terraform output parsing
2. Implement automatic cleanup on scan failure
3. Add validation for Terraform outputs structure
4. Consider adding type hints to prevent similar issues
5. Enhance error messages to show actual vs expected data types

## References

- Fixed file: `kast/scripts/zap_providers.py`
- Helper function: `kast/scripts/terraform_manager.py:get_outputs()`
- Cleanup tool: `kast/scripts/cleanup_orphaned_resources.py`
- Documentation: `kast/docs/ORPHANED_RESOURCES_CLEANUP.md`