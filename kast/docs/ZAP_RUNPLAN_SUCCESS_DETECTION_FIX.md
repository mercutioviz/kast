# ZAP Automation Plan Success Detection Fix

**Date:** 2026-01-05
**Issue:** ZAP automation plans were reported as failed even though they were successfully running
**Component:** `kast/scripts/zap_providers.py` - `RemoteZapProvider.upload_automation_plan()`

## Problem

The ZAP plugin was incorrectly detecting failures when launching automation plans via the remote provider. The issue manifested as:

```
[DEBUG] [zap]: ZAP API response: {'planId': '4'}
[DEBUG] [zap]: Failed to run automation plan: Unknown error
[DEBUG] [zap]: ERROR: Failed to upload/execute automation plan
```

However, the plan was actually running successfully:
```bash
curl "http://54.68.165.165:8080/JSON/automation/view/planProgress/?apikey=kast01&planId=4"
{"planId":4,"started":"2026-01-05T22:02:36.069Z","info":["Job spider started",...]}
```

## Root Cause

The `upload_automation_plan()` method was checking for `Result == 'OK'` in the API response:

```python
if run_response and run_response.get('Result') == 'OK':
    self.debug("Automation plan uploaded and initiated successfully")
    return True
else:
    error = run_response.get('message', 'Unknown error')
    self.debug(f"Failed to run automation plan: {error}")
    return False
```

**However, ZAP's `/JSON/automation/action/runPlan/` API returns `{'planId': 'N'}` on success, not `{'Result': 'OK'}`.**

## Solution

Changed the success detection to check for the presence of `planId` in the response:

```python
# Check for planId in response (indicates success)
if run_response and 'planId' in run_response:
    self.plan_id = run_response.get('planId')
    self.debug(f"✓ Automation plan initiated successfully (planId: {self.plan_id})")
    
    # OPTIONAL: Verify plan is actually running
    try:
        progress_response = self.zap_client._make_request(
            '/JSON/automation/view/planProgress/',
            params={'planId': self.plan_id}
        )
        
        if progress_response and 'started' in progress_response:
            self.debug(f"✓ Plan confirmed running (started: {progress_response.get('started')})")
    except Exception as e:
        self.debug(f"Note: Plan progress check skipped: {e}")
    
    return True
```

## Changes Made

### 1. Added `plan_id` Instance Variable
```python
def __init__(self, config, debug_callback=None):
    super().__init__(config, debug_callback)
    self.plan_id = None  # Store planId for monitoring
```

### 2. Updated Success Detection Logic
- **Primary check:** Look for `planId` in response (modern ZAP API)
- **Secondary check:** Verify plan is running with `planProgress` API call
- **Fallback check:** Still support legacy `Result: OK` format for backward compatibility

### 3. Enhanced Debug Logging
- Added ✓ checkmarks for successful operations
- Include `planId` in success messages
- Include `started` timestamp from progress verification
- Clear distinction between errors and informational notes

## Testing

To verify the fix works:

1. **Run a ZAP scan in remote mode:**
```bash
kast -t example.com -v -m active \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://your-zap:8080 \
  --set zap.remote.api_key=your-key \
  --zap-profile=quick
```

2. **Expected debug output:**
```
[DEBUG] [zap]: Step 2: Running automation plan at: /home/zap/.ZAP/transfer/kast_automation_plan.yaml
[DEBUG] [zap]: ZAP API response: {'planId': '4'}
[DEBUG] [zap]: ✓ Automation plan initiated successfully (planId: 4)
[DEBUG] [zap]: ✓ Plan confirmed running (started: 2026-01-05T22:02:36.069Z)
```

3. **Verify scan continues:**
The scan should proceed to monitor progress and download results, rather than failing immediately.

## API Reference

### ZAP Automation Framework APIs Used

1. **runPlan** - Execute an automation plan
   ```
   POST /JSON/automation/action/runPlan/?apikey=KEY
   Data: {"filePath": "/path/to/plan.yaml"}
   Response: {"planId": "N"}
   ```

2. **planProgress** - Check plan execution status
   ```
   GET /JSON/automation/view/planProgress/?apikey=KEY&planId=N
   Response: {
     "planId": N,
     "started": "ISO8601 timestamp",
     "finished": "ISO8601 timestamp or empty",
     "info": ["Job spider started", ...],
     "warn": [...],
     "error": [...]
   }
   ```

## Future Improvements

Consider using `planId` for more targeted monitoring:
- Instead of generic scan status polling, use `planProgress` specifically
- Track individual job completion from the progress info
- Better error handling if a plan errors out mid-execution

## Related Issues

- Initial implementation: `ZAP_MULTI_MODE_IMPLEMENTATION.md`
- Remote mode setup: `ZAP_REMOTE_MODE_QUICK_START.md`
- File upload fix: `ZAP_REMOTE_FILE_UPLOAD_FIX.md`
