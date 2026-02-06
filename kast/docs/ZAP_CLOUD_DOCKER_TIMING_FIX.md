# ZAP Cloud Docker Installation Timing Fix

**Date:** 2026-01-23  
**Issue:** Cloud-provisioned ZAP instances failed with "docker: command not found"  
**Root Cause:** Race condition between SSH connection and startup script completion  

## Problem Description

When using ZAP cloud mode (AWS, Azure, or GCP), the plugin would fail immediately after provisioning with:

```
bash: line 1: docker: command not found
TypeError: tuple indices must be integers or slices, not str
```

### Two Issues Identified

1. **Timing Race Condition**: KAST attempted to run Docker commands immediately after establishing SSH connection, before the cloud-init/user_data startup script completed Docker installation

2. **Code Bug**: Incorrect handling of SSH executor return values
   - `ssh_executor.execute_command()` returns a tuple: `(exit_code, stdout, stderr)`
   - Code incorrectly treated it as a dict: `result['exit_code']`

## Solution

### 1. Added Startup Script Completion Check

All Terraform configs (AWS, Azure, GCP) create a `/tmp/zap-ready` flag file when startup completes. The fix now:
- Waits for this flag file (up to 10 minutes)
- Polls every 10 seconds
- Proceeds to Docker verification even if flag not found (defensive)

```python
# Wait for startup script to complete (it creates /tmp/zap-ready flag)
self.debug("Waiting for startup script to complete...")
if not self.ssh_executor.wait_for_file('/tmp/zap-ready', timeout=600, poll_interval=10):
    self.debug("Warning: Startup script completion flag not found, checking Docker directly...")
```

### 2. Added Docker Installation Verification

After startup script check, explicitly verify Docker is installed:
- Tests `docker --version` command
- Retries for up to 5 minutes
- 10-second intervals between checks
- Provides clear progress messages

```python
# Verify Docker is installed and ready
self.debug("Verifying Docker installation...")
max_docker_wait = 300  # 5 minutes
docker_ready = False
docker_wait_start = time.time()

while time.time() - docker_wait_start < max_docker_wait:
    exit_code, stdout, stderr = self.ssh_executor.execute_command('docker --version')
    if exit_code == 0:
        self.debug(f"✓ Docker is installed: {stdout.strip()}")
        docker_ready = True
        break
    else:
        elapsed = int(time.time() - docker_wait_start)
        self.debug(f"Docker not ready yet (waited {elapsed}s), retrying...")
        time.sleep(10)

if not docker_ready:
    return False, None, {"error": "Docker installation failed or timed out"}
```

### 3. Fixed SSH Command Result Handling

Changed all `ssh_executor.execute_command()` calls to properly unpack tuple:

**Before (incorrect):**
```python
result = self.ssh_executor.execute_command(zap_cmd)
if result['exit_code'] != 0:
    self.debug(f"Failed: {result['stderr']}")
```

**After (correct):**
```python
exit_code, stdout, stderr = self.ssh_executor.execute_command(zap_cmd)
if exit_code != 0:
    self.debug(f"Failed: {stderr}")
```

## Files Modified

- `kast/scripts/zap_providers.py`:
  - `CloudZapProvider.provision()` - Added startup completion and Docker readiness checks
  - `CloudZapProvider.provision()` - Fixed SSH command tuple unpacking (3 locations)
  - `CloudZapProvider.download_results()` - Fixed SSH command tuple unpacking

## Terraform Configs (Already Correct)

All three Terraform configurations were already correctly installing Docker:

1. **AWS** (`kast/terraform/aws/main.tf`)
2. **Azure** (`kast/terraform/azure/main.tf`)  
3. **GCP** (`kast/terraform/gcp/main.tf`)

Each includes:
- Docker installation via `get.docker.com` script
- nginx reverse proxy setup
- ZAP container startup
- `/tmp/zap-ready` flag creation

The issue was NOT missing Docker installation, but improper wait logic on the KAST side.

## Testing

To verify the fix:

```bash
# Test with AWS (or azure/gcp)
cd /opt/kast
python3 -m kast.main \
  --target https://example.com \
  --plugins zap \
  --set zap.mode=cloud \
  --set zap.cloud.cloud_provider=aws \
  --set zap.cloud.aws.region=us-east-1
```

Expected behavior:
1. ✅ Terraform provisions instance
2. ✅ SSH connection established
3. ✅ Waits for `/tmp/zap-ready` flag (up to 10 min)
4. ✅ Verifies Docker installation
5. ✅ Starts ZAP container
6. ✅ Scan proceeds normally

## Timeline Improvements

With these fixes, the cloud provisioning timeline is:

1. **0-3 min**: Terraform provisioning
2. **0-2 min**: SSH connection establishment  
3. **0-10 min**: Startup script completion wait
4. **0-5 min**: Docker installation verification
5. **0-2 min**: ZAP container start
6. **Total**: ~5-15 minutes (depending on cloud provider)

The fix eliminates premature failures while still providing reasonable timeouts.

## Related Documentation

- `kast/docs/ZAP_CLOUD_PLUGIN_GUIDE.md` - Cloud mode overview
- `kast/docs/ZAP_MULTI_MODE_GUIDE.md` - All ZAP modes
- `kast/terraform/*/main.tf` - Infrastructure definitions