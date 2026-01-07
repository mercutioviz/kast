# ZAP Progress Snapshots Implementation

**Date:** 2026-01-06
**Feature:** Real-time progress snapshots during ZAP scan execution
**Components:** `zap_api_client.py`, `zap_providers.py`, `zap_plugin.py`

## Overview

The ZAP plugin now writes real-time progress snapshots to the output directory during scan execution. This provides visibility into long-running scans and enables monitoring of scan progress, alert accumulation, and component status.

## Features

✅ **Real-time visibility** - Track scan progress without waiting for completion  
✅ **Progress metrics** - Spider/active scan percentages, alert counts by risk level  
✅ **Job tracking** - See which automation framework jobs are running/completed  
✅ **Error detection** - View errors and warnings as they occur  
✅ **Debugging aid** - Preserved progress data helps diagnose scan issues  

## Progress Snapshot File

### Location

Progress snapshots are written to:
```
kast_results/<target>-<timestamp>/zap_scan_progress.json
```

The file is **overwritten** on each poll interval with updated metrics.

### File Format

```json
{
  "scan_started": "2026-01-06T15:00:00.000Z",
  "last_updated": "2026-01-06T15:05:30.123Z",
  "elapsed_seconds": 330,
  "plan_id": 4,
  "status": "running",
  "finished": "",
  "progress": {
    "spider_percent": 85,
    "active_scan_percent": 42,
    "passive_scan_queue": 23
  },
  "alerts": {
    "total": 138,
    "by_risk": {
      "High": 3,
      "Medium": 12,
      "Low": 45,
      "Informational": 78
    }
  },
  "job_updates": [
    "Job spider started",
    "Job spider finished",
    "Job activeScan started"
  ],
  "warnings": [],
  "errors": []
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `scan_started` | string | ISO 8601 timestamp when plan execution started |
| `last_updated` | string | ISO 8601 timestamp of this snapshot |
| `elapsed_seconds` | integer | Seconds since monitoring began |
| `plan_id` | integer/string | Automation framework plan ID |
| `status` | string | `"running"` or `"completed"` |
| `finished` | string | Empty while running, ISO timestamp when complete |
| `progress.spider_percent` | integer | Spider scan progress (0-100%) |
| `progress.active_scan_percent` | integer | Active scan progress (0-100%) |
| `progress.passive_scan_queue` | integer | Number of passive scan records remaining |
| `alerts.total` | integer | Total alerts found so far |
| `alerts.by_risk` | object | Alert counts grouped by risk level |
| `job_updates` | array | All automation framework job status messages |
| `warnings` | array | Warning messages from plan execution |
| `errors` | array | Error messages (if any) |

## Implementation Details

### 1. ZAPAPIClient._write_progress_snapshot()

The core method that collects metrics and writes the snapshot file:

```python
def _write_progress_snapshot(self, plan_id, progress, scan_start_time, 
                            elapsed_seconds, output_dir, final=False):
```

**Metrics Collected:**

1. **Plan Progress** (from `planProgress` API)
   - Started/finished timestamps
   - Job updates (info array)
   - Warnings
   - Errors

2. **Alert Statistics** (from `alertsSummary` and `numberOfAlerts` APIs)
   - Total alert count
   - Breakdown by risk level (High/Medium/Low/Informational)

3. **Component Status** (from component-specific APIs)
   - Spider progress percentage (`/JSON/spider/view/status/`)
   - Active scan progress percentage (`/JSON/ascan/view/status/`)
   - Passive scan queue size (`/JSON/pscan/view/recordsToScan/`)

**Error Handling:**

Each API call is wrapped in try/except to ensure progress snapshot writing doesn't fail the scan if one metric becomes unavailable:

```python
try:
    spider_status = self._make_request('/JSON/spider/view/status/')
    if spider_status:
        spider_percent = int(spider_status.get('status', 0))
except Exception as e:
    self.debug(f"Could not fetch spider status: {e}")
    # Continue with spider_percent = 0 (default)
```

### 2. Integration with wait_for_plan_completion()

The progress snapshot is written during each poll cycle:

```python
def wait_for_plan_completion(self, plan_id, timeout=3600, poll_interval=30, output_dir=None):
    while time.time() - start_time < timeout:
        progress = self.get_plan_progress(plan_id)
        
        # Write progress snapshot if output_dir provided
        if output_dir:
            self._write_progress_snapshot(
                plan_id=plan_id,
                progress=progress,
                scan_start_time=scan_start_time,
                elapsed_seconds=int(time.time() - start_time),
                output_dir=output_dir
            )
        
        # Check if finished...
        if progress.get('finished'):
            # Write final snapshot
            if output_dir:
                self._write_progress_snapshot(..., final=True)
            break
```

**Final Snapshot:**

When the plan completes, a final snapshot is written with:
- `status: "completed"`
- `finished: "<timestamp>"`
- Final alert counts and risk breakdown

### 3. Plugin Integration

The ZapPlugin passes the output directory to enable progress tracking:

```python
# In ZapPlugin.run()
if use_automation and plan_id:
    self.debug(f"Progress snapshots will be written to: {output_dir}/zap_scan_progress.json")
    
    success, progress = self.provider.wait_for_plan_completion(
        timeout=timeout_minutes * 60,
        poll_interval=poll_interval,
        output_dir=output_dir  # Enable progress snapshots
    )
```

## Usage Examples

### Monitoring Progress in Real-Time

**Terminal 1 - Run scan:**
```bash
kast -t example.com -v -m active \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://your-zap:8080 \
  --enabled-plugins=zap
```

**Terminal 2 - Watch progress:**
```bash
# Simple approach - watch file
watch -n 5 cat kast_results/example.com-*/zap_scan_progress.json

# Or pretty print with jq
watch -n 5 'cat kast_results/example.com-*/zap_scan_progress.json | jq .'

# Monitor specific metrics
watch -n 5 'cat kast_results/example.com-*/zap_scan_progress.json | jq "{elapsed: .elapsed_seconds, alerts: .alerts.total, spider: .progress.spider_percent, ascan: .progress.active_scan_percent}"'
```

### Post-Scan Analysis

After a scan completes (or fails), examine the progress file to understand what happened:

```bash
# Get final snapshot
jq '.' kast_results/example.com-20260106-150000/zap_scan_progress.json

# Check total runtime
jq '.elapsed_seconds' zap_scan_progress.json

# See all job updates
jq '.job_updates[]' zap_scan_progress.json

# Check for errors
jq '.errors' zap_scan_progress.json
```

### Building a Progress Dashboard

The JSON format makes it easy to build monitoring dashboards:

```python
import json
import time
from pathlib import Path

def monitor_scan(results_dir):
    """Monitor ZAP scan progress"""
    progress_file = Path(results_dir) / "zap_scan_progress.json"
    
    while True:
        if not progress_file.exists():
            print("Waiting for scan to start...")
            time.sleep(5)
            continue
        
        with open(progress_file) as f:
            data = json.load(f)
        
        # Display progress
        print(f"\n{'='*60}")
        print(f"Elapsed: {data['elapsed_seconds']}s | Status: {data['status']}")
        print(f"Spider: {data['progress']['spider_percent']}% | "
              f"Active Scan: {data['progress']['active_scan_percent']}%")
        print(f"Alerts: {data['alerts']['total']} total")
        print(f"  High: {data['alerts']['by_risk'].get('High', 0)}, "
              f"Medium: {data['alerts']['by_risk'].get('Medium', 0)}, "
              f"Low: {data['alerts']['by_risk'].get('Low', 0)}")
        
        if data['status'] == 'completed':
            print("\n✓ Scan completed!")
            break
        
        time.sleep(10)

# Usage
monitor_scan("kast_results/example.com-20260106-150000")
```

## API Endpoints Used

The progress snapshot feature queries these ZAP APIs:

### 1. planProgress (Core Data)
```
GET /JSON/automation/view/planProgress/?planId=N
```
Returns job status, warnings, errors.

### 2. alertsSummary (Risk Breakdown)
```
GET /JSON/core/view/alertsSummary/
```
Returns alert counts by risk level:
```json
{
  "High": 3,
  "Medium": 12,
  "Low": 45,
  "Informational": 78
}
```

### 3. numberOfAlerts (Total Count)
```
GET /JSON/core/view/numberOfAlerts/
```
Returns:
```json
{
  "numberOfAlerts": "138"
}
```

### 4. Spider Status
```
GET /JSON/spider/view/status/
```
Returns progress percentage:
```json
{
  "status": "85"
}
```

### 5. Active Scan Status
```
GET /JSON/ascan/view/status/
```
Returns progress percentage:
```json
{
  "status": "42"
}
```

### 6. Passive Scan Queue
```
GET /JSON/pscan/view/recordsToScan/
```
Returns number of records pending:
```json
{
  "recordsToScan": "23"
}
```

## Configuration

### Poll Interval

The progress snapshot is updated at each poll interval:

```yaml
# In zap_config.yaml
zap_config:
  poll_interval_seconds: 30  # Update every 30 seconds
```

**CLI Override:**
```bash
--set zap.zap_config.poll_interval_seconds=15
```

**Considerations:**
- **Shorter interval** (10-15s) = More frequent updates, more API calls
- **Longer interval** (60s+) = Less overhead, less granular tracking
- **Recommended:** 30 seconds for most scans

### Disabling Progress Snapshots

Currently, progress snapshots are always enabled for automation framework scans. To disable (if needed in future):

The feature is tied to `output_dir` parameter - it only writes if output_dir is provided.

## Performance Impact

### API Call Overhead

Per poll cycle, the plugin makes **6 additional API calls**:
1. alertsSummary
2. numberOfAlerts
3. spider/view/status
4. ascan/view/status
5. pscan/view/recordsToScan
6. planProgress (already called)

**Impact Analysis:**
- At 30-second intervals for a 10-minute scan: ~120 extra API calls
- Each call takes ~50-100ms
- Total overhead: ~6-12 seconds over 10 minutes (**< 2% impact**)

### File I/O

The snapshot file is small (~1-2 KB) and overwritten each cycle. File I/O is negligible.

### Recommendations

✅ Safe for all scan types and durations  
✅ No noticeable performance impact  
✅ Benefits far outweigh minimal overhead  

## Error Handling

### Graceful Degradation

If any metric API fails, the snapshot continues with default values:

```python
# Example: spider status unavailable
try:
    spider_status = self._make_request('/JSON/spider/view/status/')
    spider_percent = int(spider_status.get('status', 0))
except Exception as e:
    self.debug(f"Could not fetch spider status: {e}")
    spider_percent = 0  # Default to 0
```

### Snapshot Write Failures

If the entire snapshot write fails, it's logged but doesn't abort the scan:

```python
try:
    # Write snapshot...
except Exception as e:
    # Don't fail the scan if progress writing fails
    self.debug(f"Warning: Failed to write progress snapshot: {e}")
```

## Troubleshooting

### Issue: Progress file not created

**Cause:** Output directory not passed to wait_for_plan_completion()

**Solution:** Verify plugin calls provider with output_dir:
```python
success, progress = self.provider.wait_for_plan_completion(
    timeout=timeout,
    poll_interval=poll_interval,
    output_dir=output_dir  # Must be provided
)
```

### Issue: Metrics show 0 despite scan running

**Possible causes:**
1. ZAP API not responding to specific endpoints
2. API format changed in newer ZAP version
3. Network connectivity issues (remote mode)

**Debug:** Check KAST debug logs for API errors:
```bash
grep "Could not fetch" kast_results/*/debug.log
```

### Issue: Snapshot not updating

**Cause:** Scan may be stalled or timing out

**Solution:** 
1. Check `elapsed_seconds` - if increasing but no job_updates, scan is stalled
2. Review ZAP logs: `docker logs <zap-container>`
3. Check ZAP UI if available: `http://zap-host:8080`

## Future Enhancements

Potential improvements to consider:

### 1. Historical Log Mode

Instead of overwriting, append to a log file:
```json
// zap_scan_progress.log
{"timestamp": "2026-01-06T15:00:00Z", "alerts": 0, "spider": 0}
{"timestamp": "2026-01-06T15:00:30Z", "alerts": 12, "spider": 15}
{"timestamp": "2026-01-06T15:01:00Z", "alerts": 45, "spider": 30}
```

This creates a timeline of scan progression.

### 2. Progress Percentage Calculation

Calculate overall progress based on:
- Number of completed jobs vs total jobs
- Weighted average of spider/ascan progress
- Alert discovery rate

```json
{
  "overall_progress": 67,
  "estimated_completion": "2026-01-06T15:10:00Z"
}
```

### 3. Real-Time Alert Streaming

Stream individual alerts as they're discovered:
```json
{
  "new_alerts_since_last_update": [
    {
      "alert": "SQL Injection",
      "risk": "High",
      "url": "https://example.com/login"
    }
  ]
}
```

### 4. Configurable Metrics

Allow users to choose which metrics to track:
```yaml
progress_tracking:
  enabled: true
  metrics:
    - plan_progress
    - alerts
    - spider_status
    # Disable ascan/pscan if not needed
```

### 5. Webhook Notifications

Send progress updates to external systems:
```yaml
progress_tracking:
  webhook_url: https://monitoring.example.com/webhook
  notify_on:
    - high_risk_alert
    - scan_25_percent
    - scan_50_percent
    - scan_complete
```

## Related Documentation

- `ZAP_AUTOMATION_PLAN_MONITORING.md` - Plan monitoring implementation
- `ZAP_RUNPLAN_SUCCESS_DETECTION_FIX.md` - Plan execution detection
- `ZAP_REMOTE_MODE_QUICK_START.md` - Remote mode setup
- `ZAP_MULTI_MODE_IMPLEMENTATION.md` - Overall architecture

## Testing

### Manual Test

```bash
# Terminal 1: Start scan
kast -t example.com -v -m active \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://your-zap:8080 \
  --enabled-plugins=zap

# Terminal 2: Monitor progress
watch -n 5 'cat kast_results/example.com-*/zap_scan_progress.json | jq "{elapsed: .elapsed_seconds, alerts: .alerts.total, status: .status}"'
```

### Verify Metrics

After scan completes:
```bash
cd kast_results/example.com-*

# Check final snapshot exists
ls -lh zap_scan_progress.json

# Verify structure
jq 'keys' zap_scan_progress.json

# Should show: ["alerts", "elapsed_seconds", "errors", "finished", "job_updates", "last_updated", "plan_id", "progress", "scan_started", "status", "warnings"]

# Verify status is completed
jq '.status' zap_scan_progress.json
# Should output: "completed"

# Check alerts were tracked
jq '.alerts' zap_scan_progress.json
```

## Conclusion

The progress snapshot feature provides essential visibility into long-running ZAP scans without impacting performance. The JSON format enables easy integration with monitoring tools, and graceful error handling ensures scan reliability.
