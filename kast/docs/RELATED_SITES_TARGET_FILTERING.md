# Related Sites Target Filtering Implementation

## Overview

This document describes the implementation of target domain filtering in the `related_sites` plugin to prevent duplication in scan results.

## Problem Statement

**Bug:** The related_sites plugin was discovering and reporting the original target domain as a "related site".

**Example:**
- Target: `www.foo.com`
- Apex domain: `foo.com`
- Plugin discovers all subdomains of `foo.com` including `www.foo.com`
- Result: `www.foo.com` appears in related sites list ❌

This is incorrect because "related sites" should only include OTHER subdomains, not the target itself.

## Solution

Implemented a filtering mechanism that:
1. Normalizes hostnames for comparison (case-insensitive, protocol/port agnostic)
2. Filters out the target domain before HTTP probing
3. Tracks filtering statistics for transparency

## Implementation Details

### 1. Hostname Normalization (`_normalize_hostname`)

A new helper method that normalizes hostnames for reliable comparison:

```python
def _normalize_hostname(self, hostname):
    """
    Normalize a hostname for comparison by removing protocols, ports,
    and converting to lowercase.
    
    Examples:
      www.example.com -> www.example.com
      WWW.EXAMPLE.COM -> www.example.com
      http://www.example.com -> www.example.com
      www.example.com:8080 -> www.example.com
    """
```

**Normalization steps:**
1. Remove protocol (http://, https://)
2. Remove port number (:80, :443, :8080, etc.)
3. Remove trailing slashes
4. Convert to lowercase

### 2. Filtering Logic

Implemented in the `run()` method after subfinder discovers subdomains:

```python
# Step 2.5: Filter out the original target to avoid duplication
original_target_normalized = self._normalize_hostname(target)
filtered_subdomains = []
filtered_count = 0

for subdomain in subdomains:
    subdomain_normalized = self._normalize_hostname(subdomain)
    if subdomain_normalized != original_target_normalized:
        filtered_subdomains.append(subdomain)
    else:
        filtered_count += 1
        self.debug(f"Filtered out target domain: {subdomain}")
```

**Key features:**
- Case-insensitive comparison
- Protocol/port agnostic
- Preserves original subdomain strings (only normalized for comparison)
- Logs filtered entries for debugging

### 3. Enhanced Statistics

Updated statistics tracking to include filtering information:

```python
"statistics": {
    "total_discovered": len(subdomains),           # All discovered
    "filtered_duplicates": filtered_count,         # Filtered out
    "total_related": len(filtered_subdomains),     # Actually scanned
    "total_live": len(live_hosts),
    "total_dead": len(dead_hosts),
    "response_rate": ...,
    ...
}
```

### 4. Updated Results Structure

```python
final_results = {
    "target": target,
    "apex_domain": apex_domain,
    "scanned_domain": scan_target,
    "total_subdomains": len(subdomains),
    "subdomains": subdomains,                      # All discovered
    "filtered_target_duplicates": filtered_count,  # NEW
    "related_subdomains": filtered_subdomains,     # NEW: Actually scanned
    "live_hosts": live_hosts,
    "dead_hosts": dead_hosts,
    ...
}
```

## Edge Cases Handled

### Case Sensitivity
```python
Target: www.example.com
Subdomain: WWW.EXAMPLE.COM
Result: Filtered (same domain, different case)
```

### Protocol Prefixes
```python
Target: www.example.com
Subdomain: https://www.example.com
Result: Filtered (same domain, protocol ignored)
```

### Port Numbers
```python
Target: www.example.com
Subdomain: www.example.com:8080
Result: Filtered (same domain, port ignored)
```

### Combined
```python
Target: www.example.com
Subdomain: https://WWW.EXAMPLE.COM:443/
Result: Filtered (same domain, all variations normalized)
```

## Benefits

### ✅ Resource Efficiency
- Avoids wasting httpx probing cycles on the target
- Reduces scan time and network traffic

### ✅ Clean Results
- Target never appears in "related sites" list
- Results are logically consistent

### ✅ Transparency
- Statistics show how many duplicates were filtered
- Debug logs record filtering decisions

### ✅ Robust Comparison
- Handles various target input formats
- Case-insensitive, protocol/port agnostic

## Testing

Comprehensive test suite in `kast/tests/test_related_sites_filtering.py`:

**Test Coverage:**
- ✅ Basic hostname normalization
- ✅ Case-insensitive comparison
- ✅ Protocol prefix handling
- ✅ Port number handling
- ✅ Combined protocol + port scenarios
- ✅ Trailing slash handling
- ✅ Exact match filtering
- ✅ No false positives (unrelated domains not filtered)
- ✅ Apex domain filtering

**Run tests:**
```bash
python -m pytest kast/tests/test_related_sites_filtering.py -v
```

## Example Workflow

### Before Fix
```
Target: www.foo.com
Subfinder discovers: [www.foo.com, mail.foo.com, api.foo.com]
HTTPx probes: [www.foo.com, mail.foo.com, api.foo.com]  
Results: 3 related sites (includes target ❌)
```

### After Fix
```
Target: www.foo.com
Subfinder discovers: [www.foo.com, mail.foo.com, api.foo.com]
Filter: Removes www.foo.com (target)
HTTPx probes: [mail.foo.com, api.foo.com]
Results: 2 related sites (excludes target ✅)
Statistics: filtered_duplicates: 1
```

## Backward Compatibility

- Existing result fields preserved
- New fields added (non-breaking):
  - `filtered_target_duplicates`
  - `related_subdomains`
  - `statistics.filtered_duplicates`
  - `statistics.total_related`

## Future Enhancements

Potential improvements:
1. Filter multiple target variations if provided
2. Option to include/exclude target via configuration
3. Filter by custom patterns (e.g., internal domains)

## References

- Plugin: `kast/plugins/related_sites_plugin.py`
- Tests: `kast/tests/test_related_sites_filtering.py`
- Related docs: `kast/docs/RELATED_SITES_PLUGIN.md`

## Error Handling

The plugin includes robust error handling in the `post_process` method to gracefully handle failure cases:

**Issue:** When the plugin fails (e.g., no subdomains discovered), the `run()` method returns a result where the `results` field is a string error message instead of a dict. This caused an `AttributeError` when `post_process` tried to call `.get()` on the string.

**Solution:** The `post_process` method now detects when `findings` is a string (failure case) and creates a minimal processed output with:
- Empty findings dict
- findings_count: 0
- Error message in summary, details, and executive_summary
- Valid structure for report generation

This ensures the plugin always produces valid processed output, even when execution fails.

**Test Coverage:** See `kast/tests/test_related_sites_error_handling.py` for comprehensive error handling tests.

## Version History

- **v1.1** (2025-12-31): 
  - Added target filtering to prevent duplication
  - Fixed error handling in post_process for failure cases
- **v1.0** (Initial): Basic subdomain discovery and HTTP probing

---

**Last Updated:** 2025-12-31  
**Author:** KAST Development Team
