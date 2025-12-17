# Related Sites Plugin Post-Processing Bug Fix

## Issue Date
December 16, 2025

## Problem Description

The Related Sites plugin was not correctly displaying scan results in reports. Despite successful scans discovering subdomains and live hosts, the processed output showed:
- 0 subdomains discovered
- 0 live hosts
- 0% response rate
- "No live hosts discovered" message

## Root Cause Analysis

### Issue 1: Incorrect Data Structure Access

The `post_process()` method was not correctly extracting results from the nested data structure.

**Data Structure:**
```python
raw_output = {
    "name": "related_sites",
    "disposition": "success",
    "results": {
        "total_subdomains": 16,
        "live_hosts": [...],
        "statistics": {...},
        # ... actual scan data
    }
}
```

**Original Code:**
```python
def post_process(self, raw_output, output_dir):
    findings = raw_output if isinstance(raw_output, dict) else {}
    # This passed the entire raw_output dict, not just results
```

**Problem:** Helper methods tried to access `findings.get("statistics")` directly, but the data was actually at `findings["results"]["statistics"]`.

### Issue 2: Port Type Mismatch

HTTPx JSON output stored port numbers as strings (e.g., `"443"`), but the code compared them as integers.

**Error:** `'<=' not supported between instances of 'int' and 'str'`

### Issue 3: Status Code Type Mismatch

Similar issue with status codes being stored as strings in JSON but compared as integers in HTML generation.

## Solutions Implemented

### Fix 1: Extract Results Before Processing

Modified `post_process()` to extract the nested `results` dictionary:

```python
def post_process(self, raw_output, output_dir):
    # Extract the actual results from the nested structure
    findings = raw_output.get("results", {}) if isinstance(raw_output, dict) else {}
    # Now findings contains the actual scan data
```

**File:** `kast/plugins/related_sites_plugin.py`  
**Line:** ~457

### Fix 2: Normalize Port Numbers

Added type conversion when parsing HTTPx output:

```python
# Port can be string or int from httpx, normalize to int
port = int(data.get('port', 0)) if data.get('port') else 0
```

**File:** `kast/plugins/related_sites_plugin.py`  
**Line:** ~333

### Fix 3: Handle Status Code Types

Added type conversion and validation in HTML generation:

```python
# Convert status to int for comparison (it may be string from JSON)
status_int = int(status) if str(status).isdigit() else 0
status_class = "status-success" if 200 <= status_int < 300 else ...
```

**File:** `kast/plugins/related_sites_plugin.py`  
**Line:** ~644

## Verification

### Test Case
Scanned: `waas.cudalabx.net`

### Before Fix
```
Summary: Discovered 0 subdomain(s), 0 responding to HTTP requests (0.0% response rate)
Executive Summary:
  - Discovered 0 related subdomain(s), 0 responding to HTTP requests (0.0% response rate)
```

### After Fix
```
Summary: Discovered 16 subdomain(s), 8 responding to HTTP requests (50.0% response rate)
Executive Summary:
  - Discovered 16 related subdomain(s), 8 responding to HTTP requests (50.0% response rate)
  - Most common technologies: Bootstrap (4), jQuery:1.8.2 (2), Apache HTTP Server:2.4.58 (2)

Statistics:
  total_discovered: 16
  total_live: 8
  total_dead: 12
  response_rate: 50.0
  unique_technologies: 15
```

## Impact

- **Severity:** High (complete data loss in reports)
- **Scope:** All Related Sites plugin scans
- **User Impact:** Reports showed no results despite successful scans
- **Resolution:** Complete - all data now displays correctly

## Testing Performed

1. ✅ Report regeneration with existing scan data
2. ✅ Verification of summary statistics
3. ✅ Verification of executive summary
4. ✅ Verification of detailed findings
5. ✅ HTML report generation
6. ✅ Port number handling
7. ✅ Status code handling

## Files Modified

1. `kast/plugins/related_sites_plugin.py`
   - Modified `post_process()` method (line ~457)
   - Modified `_parse_httpx_results()` method (line ~333)
   - Modified `_generate_custom_html()` method (line ~644)

## Related Documentation

- Plugin Documentation: `kast/docs/RELATED_SITES_PLUGIN.md`
- Implementation Summary: `kast/docs/RELATED_SITES_IMPLEMENTATION_SUMMARY.md`
- Rate Limiting Feature: `kast/docs/RELATED_SITES_RATE_LIMITING.md`

## Lessons Learned

1. **Data Structure Awareness:** Always verify nested data structures when passing between methods
2. **Type Consistency:** JSON serialization can change numeric types to strings
3. **Defensive Programming:** Always handle type conversions when dealing with external data
4. **Test Report Generation:** Always test post-processing with actual scan data

## Prevention Measures

1. Add unit tests for post-processing methods
2. Include type hints in method signatures
3. Document data structure expectations clearly
4. Validate data types at method boundaries

---

**Status:** Resolved  
**Version:** 1.1  
**Date:** December 16, 2025
