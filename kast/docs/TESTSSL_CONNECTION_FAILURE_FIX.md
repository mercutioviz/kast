# TestSSL Connection Failure Handling Fix

## Issue Description

The testssl plugin was not properly handling connection failures when scanning targets. When testssl encountered a connection problem (such as being unable to connect to a target due to firewall rules, network issues, or the service being down), the plugin would crash or produce incorrect results.

### Error Scenario

When testssl cannot connect to a target, it returns a JSON structure like:

```json
{
  "scanResult": [
    {
      "finding": "Can't connect to '85.239.246.208:443' Make sure a firewall is not between you and your scanning target!",
      "id": "scanProblem",
      "severity": "FATAL"
    }
  ]
}
```

The plugin's `post_process()` method was attempting to extract `vulnerabilities` and `cipherTests` from the `scanResult`, which don't exist in connection failure scenarios. This caused the plugin to fail silently or produce misleading output.

## Solution

Added early detection logic in the `post_process()` method to check for scan problems before attempting to process vulnerability and cipher data:

```python
# Check for scan problems (connection failures, etc.)
if scan_data.get("id") == "scanProblem" and scan_data.get("severity") == "FATAL":
    scan_problem_msg = scan_data.get("finding", "Unknown scan problem")
    self.debug(f"Scan problem detected: {scan_problem_msg}")
    
    # Build processed result for scan failure
    processed = {
        "plugin-name": self.name,
        "plugin-description": self.description,
        "plugin-display-name": getattr(self, 'display_name', None),
        "plugin-website-url": getattr(self, 'website_url', None),
        "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
        "findings": findings,
        "summary": summary or f"{self.name} did not produce any findings",
        "details": f"Unable to complete SSL/TLS scan:\n\n{scan_problem_msg}",
        "issues": [],
        "executive_summary": f"SSL/TLS scan could not be completed. {scan_problem_msg}",
        "report": report_notes
    }
    
    # Save and return early
    processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
    with open(processed_path, "w") as f:
        json.dump(processed, f, indent=2)
    
    return processed_path
```

## Key Changes

1. **Early Detection**: Check for `scanProblem` ID and `FATAL` severity before attempting normal processing
2. **Clear Error Messaging**: Extract the connection failure message and include it in both the details and executive summary
3. **Empty Issues List**: Return an empty issues list since no actual vulnerabilities were detected
4. **Graceful Handling**: Return a properly formatted result that integrates cleanly with the report generation system

## Report Output

When a connection failure occurs, the report will now show:

- **Details**: "Unable to complete SSL/TLS scan: [specific error message]"
- **Executive Summary**: "SSL/TLS scan could not be completed. [specific error message]"
- **Issues**: Empty list (no false positives)

## Testing

A comprehensive test suite was added in `kast/tests/test_testssl_connection_failure.py` that validates:

1. Connection failures are properly detected and handled
2. Error messages are correctly extracted and formatted
3. Normal successful scans continue to work as expected
4. No regression in existing functionality

Run tests with:
```bash
python -m unittest kast.tests.test_testssl_connection_failure -v
```

## Related Files

- **Modified**: `kast/plugins/testssl_plugin.py`
- **Added**: `kast/tests/test_testssl_connection_failure.py`
- **Documentation**: `kast/docs/TESTSSL_CONNECTION_FAILURE_FIX.md`

## Date

November 20, 2025
