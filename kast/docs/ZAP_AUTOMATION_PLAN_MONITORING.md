# ZAP Automation Plan Monitoring Implementation

**Date:** 2026-01-06
**Feature:** Proper plan monitoring and JSON report download for ZAP automation framework
**Components:** `zap_api_client.py`, `zap_providers.py`, `zap_plugin.py`

## Overview

Implemented proper monitoring for ZAP automation plans instead of incorrectly relying on generic scan status APIs. The plugin now:

1. **Waits for plan completion** using `planProgress` API
2. **Downloads results** using `jsonreport` endpoint
3. **Provides real-time feedback** on plan execution progress
4. **Detects errors** during plan execution

## Problem Statement

Previously, the ZAP plugin would:
- Launch an automation plan successfully
- Immediately proceed to generic scan monitoring (spider/active scan status)
- Not actually wait for the automation plan to finish
- Try to download results before the scan completed

This resulted in incomplete or missing scan results.

## Solution Architecture

### 1. ZAPAPIClient - Plan Monitoring Methods

Added three new methods to `kast/scripts/zap_api_client.py`:

#### `get_plan_progress(plan_id)`
```python
def get_plan_progress(self, plan_id):
    """
    Get automation plan progress
    
    :param plan_id: Plan ID from runPlan response
    :return: Progress dict with started, finished, info, warn, error
    """
```

**API Endpoint:** `/JSON/automation/view/planProgress/?planId=N`

**Response Structure:**
```json
{
  "planId": 4,
  "started": "2026-01-06T00:00:00.000Z",
  "finished": "",  // Empty until complete
  "info": ["Job spider started", "Job spider finished", ...],
  "warn": ["Some warning message"],
  "error": []
}
```

#### `wait_for_plan_completion(plan_id, timeout, poll_interval)`
```python
def wait_for_plan_completion(self, plan_id, timeout=3600, poll_interval=30):
    """
    Poll automation plan progress until completion or timeout
    
    :return: Tuple of (success: bool, final_progress: dict)
    """
```

**Features:**
- Polls `planProgress` API at regular intervals
- Logs new progress updates incrementally (not duplicate messages)
- Detects completion via `finished` timestamp
- Returns success=False if plan has errors
- Returns success=False on timeout

**Debug Output Example:**
```
[DEBUG] [zap]: Waiting for plan 4 completion (timeout: 3600s, poll: 30s)
[DEBUG] [zap]:   Progress: Job spider started
[DEBUG] [zap]:   Progress: Job spider finished
[DEBUG] [zap]: Plan still running... (30s elapsed, 2 updates)
[DEBUG] [zap]:   Progress: Job activeScan started
[DEBUG] [zap]: Plan still running... (60s elapsed, 3 updates)
[DEBUG] [zap]:   Progress: Job activeScan finished
[DEBUG] [zap]: ✓ Plan completed at 2026-01-06T00:05:00.000Z
```

#### `get_json_report()`
```python
def get_json_report(self):
    """
    Download JSON report from ZAP using the jsonreport endpoint
    
    :return: Report dict
    """
```

**API Endpoint:** `/OTHER/core/other/jsonreport/`

This returns the comprehensive JSON report with all scan findings, not just alerts.

### 2. RemoteZapProvider - Plan Tracking

Modified `kast/scripts/zap_providers.py`:

#### Updated `__init__`
```python
def __init__(self, config, debug_callback=None):
    super().__init__(config, debug_callback)
    self.plan_id = None  # Store planId for monitoring
```

#### Updated `upload_automation_plan()` Return Value
**Before:** Returned `True` or `False`
**After:** Returns `plan_id` (int/string) or `None`

```python
if run_response and 'planId' in run_response:
    self.plan_id = run_response.get('planId')
    return self.plan_id  # Return planId for monitoring
else:
    return None  # Return None to indicate failure
```

This allows the plugin to track which plan is running.

#### New `wait_for_plan_completion()` Method
```python
def wait_for_plan_completion(self, timeout, poll_interval):
    """
    Wait for automation plan to complete
    
    :return: Tuple of (success: bool, progress: dict)
    """
    if not self.plan_id:
        return False, None
    
    return self.zap_client.wait_for_plan_completion(
        self.plan_id,
        timeout=timeout,
        poll_interval=poll_interval
    )
```

#### Updated `download_results()` to Use JSON Report
**Before:** Used `generate_report()` which calls `alerts` API
**After:** Uses `get_json_report()` for comprehensive results

```python
def download_results(self, output_dir, report_name):
    """Download results via JSON report API"""
    report_data = self.zap_client.get_json_report()
    
    output_path = Path(output_dir) / report_name
    with open(output_path, 'w') as f:
        json.dump(report_data, f, indent=2)
    
    return str(output_path)
```

### 3. ZapPlugin - Conditional Monitoring

Modified `kast/plugins/zap_plugin.py` run() method:

#### Track Plan ID
```python
plan_id = None  # Track plan ID for monitoring

if use_automation:
    plan_id = self.provider.upload_automation_plan(automation_plan, target)
    
    if not plan_id:
        # Upload failed
        return self.get_result_dict("fail", error_msg, timestamp)
```

#### Conditional Monitoring Logic
```python
if use_automation and plan_id:
    # Use plan-specific monitoring
    success, progress = self.provider.wait_for_plan_completion(
        timeout=timeout_minutes * 60,
        poll_interval=poll_interval
    )
    
    if not success:
        error_msg = "Automation plan execution failed or timed out"
        if progress and progress.get('error'):
            errors = progress['error']
            error_msg += f": {', '.join(errors[:3])}"
        return self.get_result_dict("fail", error_msg, timestamp)
else:
    # Use generic scan monitoring (backward compatibility)
    if not self.zap_client.wait_for_scan_completion(...):
        return self.get_result_dict("fail", "Scan timeout", timestamp)
```

**Benefits:**
- ✅ Proper monitoring for automation framework plans
- ✅ Backward compatible for direct API scans
- ✅ Clear error messages with plan errors included

## Execution Flow

### Complete Remote Mode Scan Flow

```
1. Plugin.run() called with target
   ↓
2. Load config, validate remote mode settings
   ↓
3. Create RemoteZapProvider, provision connection
   ↓
4. Load automation plan YAML
   ↓
5. Upload plan to ZAP (2-step: fileUpload + runPlan)
   → Returns plan_id (e.g., "4")
   ↓
6. Monitor plan execution
   → Poll /JSON/automation/view/planProgress/?planId=4
   → Log incremental progress updates
   → Check for 'finished' timestamp
   → Detect errors in progress.error[]
   ↓
7. Plan completes successfully
   ↓
8. Download JSON report
   → GET /OTHER/core/other/jsonreport/
   → Save to zap_report.json
   ↓
9. Load results, add metadata
   ↓
10. Cleanup (remote mode: no-op)
   ↓
11. Return success with results
```

## Testing

### Manual Test Command

```bash
# Set environment variables
export KAST_ZAP_URL="http://54.68.165.165:8080"
export KAST_ZAP_API_KEY="kast01"

# Run scan with verbose output
kast -t example.com -v -m active \
  --set zap.execution_mode=remote \
  --zap-profile=quick \
  --enabled-plugins=zap
```

### Expected Debug Output

```
[DEBUG] [zap]: Using remote provider for ZAP scan
[DEBUG] [zap]: Connecting to http://54.68.165.165:8080
[DEBUG] [zap]: ✓ Connected to ZAP v2.14.0
[DEBUG] [zap]: Uploading automation plan...
[DEBUG] [zap]: Step 1: Uploading file to ZAP...
[DEBUG] [zap]: Step 2: Running automation plan...
[DEBUG] [zap]: ✓ Automation plan initiated successfully (planId: 4)
[DEBUG] [zap]: ✓ Plan confirmed running (started: 2026-01-06T00:00:00.000Z)
[DEBUG] [zap]: Monitoring automation plan progress (timeout: 60m, poll: 30s)
[DEBUG] [zap]: Waiting for plan 4 completion (timeout: 3600s, poll: 30s)
[DEBUG] [zap]:   Progress: Job spider started
[DEBUG] [zap]:   Progress: Job spider finished
[DEBUG] [zap]: Plan still running... (30s elapsed, 2 updates)
[DEBUG] [zap]:   Progress: Job activeScan started
[DEBUG] [zap]:   Progress: Job activeScan finished
[DEBUG] [zap]: ✓ Plan completed at 2026-01-06T00:05:00.000Z
[DEBUG] [zap]: Downloading scan results...
[DEBUG] [zap]: Fetching JSON report from ZAP...
[DEBUG] [zap]: ✓ Report downloaded to .../zap_report.json
```

### Verify Report Downloaded

```bash
# Check report exists and has content
ls -lh kast_results/example.com-*/zap_report.json

# Inspect report structure
jq '.site[0] | keys' kast_results/example.com-*/zap_report.json
```

Should show: `["@name", "@host", "@port", "@ssl", "alerts"]`

## API Reference

### ZAP Automation Framework APIs

#### 1. runPlan
```
POST /JSON/automation/action/runPlan/
Data: {"filePath": "/path/to/plan.yaml", "apikey": "KEY"}
Response: {"planId": "4"}
```

#### 2. planProgress
```
GET /JSON/automation/view/planProgress/?planId=4&apikey=KEY
Response: {
  "planId": 4,
  "started": "ISO8601 timestamp",
  "finished": "ISO8601 timestamp or empty",
  "info": ["Progress message 1", "Progress message 2", ...],
  "warn": ["Warning message", ...],
  "error": ["Error message", ...]
}
```

#### 3. jsonreport
```
GET /OTHER/core/other/jsonreport/?apikey=KEY
Response: {
  "@version": "2.14.0",
  "@generated": "timestamp",
  "site": [
    {
      "@name": "https://example.com",
      "@host": "example.com",
      "@port": "443",
      "@ssl": "true",
      "alerts": [
        {
          "pluginid": "10021",
          "alertRef": "10021",
          "alert": "X-Content-Type-Options Header Missing",
          "name": "X-Content-Type-Options Header Missing",
          "riskcode": "1",
          "confidence": "2",
          "riskdesc": "Low (Medium)",
          "desc": "...",
          "instances": [...]
        }
      ]
    }
  ]
}
```

## Error Handling

### Plan Execution Errors

If a plan completes with errors in `progress.error[]`:

```python
if not success:
    error_msg = "Automation plan execution failed or timed out"
    if progress and progress.get('error'):
        errors = progress['error']
        error_msg += f": {', '.join(errors[:3])}"  # Show first 3
    return self.get_result_dict("fail", error_msg, timestamp)
```

**Example Error Output:**
```
[DEBUG] [zap]: Plan completed with 2 error(s):
[DEBUG] [zap]:   ERROR: Spider failed to start
[DEBUG] [zap]:   ERROR: Target URL unreachable
[DEBUG] [zap]: ERROR: Automation plan execution failed: Spider failed to start, Target URL unreachable
```

### Timeout Handling

If plan doesn't complete within timeout:

```python
[DEBUG] [zap]: Timeout waiting for plan 4 completion
[DEBUG] [zap]: ERROR: Automation plan execution failed or timed out
```

Returns `(False, None)` tuple.

## Configuration

### Timeout Settings

In `zap_config.yaml` or via CLI:

```yaml
zap_config:
  timeout_minutes: 60        # Max scan duration
  poll_interval_seconds: 30  # Status check frequency
```

**CLI Override:**
```bash
--set zap.zap_config.timeout_minutes=120 \
--set zap.zap_config.poll_interval_seconds=15
```

## Backward Compatibility

The implementation maintains backward compatibility:

1. **Direct API scans** (when `use_automation_framework: false`):
   - Still use `wait_for_scan_completion()` 
   - Monitor spider/ascan status via generic APIs

2. **Legacy responses** from `runPlan`:
   - Falls back to checking `Result == 'OK'`
   - Supports older ZAP versions if needed

3. **Report generation**:
   - Falls back to `generate_report()` if `get_json_report()` fails
   - Handles both new and old response formats

## Benefits

1. **✅ Accurate monitoring** - Tracks actual plan execution, not generic scans
2. **✅ Real-time feedback** - Logs progress as jobs complete
3. **✅ Error detection** - Catches and reports plan execution failures
4. **✅ Complete results** - Uses jsonreport for comprehensive findings
5. **✅ No premature exit** - Waits for plan to fully complete
6. **✅ Better UX** - Clear progress indicators and error messages

## Related Documentation

- `ZAP_RUNPLAN_SUCCESS_DETECTION_FIX.md` - Initial planId detection fix
- `ZAP_REMOTE_FILE_UPLOAD_FIX.md` - File upload implementation
- `ZAP_REMOTE_MODE_QUICK_START.md` - Remote mode setup guide
- `ZAP_MULTI_MODE_IMPLEMENTATION.md` - Overall architecture

## Future Enhancements

Potential improvements:

1. **Job-level monitoring** - Track individual job completion from `info[]`
2. **Progress percentage** - Calculate % complete based on job count
3. **Pause/resume support** - Use `pausePlan`/`resumePlan` APIs
4. **Real-time alerts** - Stream findings as they're discovered
5. **Plan validation** - Pre-validate plan YAML before upload
