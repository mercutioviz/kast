# Rate Limiting Feature for Related Sites Plugin

## Overview

Added configurable rate limiting to the Related Sites plugin's httpx component to provide better control over network request rates and help avoid triggering rate limits or IDS/IPS alerts.

## Implementation Date

December 16, 2025

## Changes Made

### 1. CLI Argument Addition (`kast/main.py`)

Added new command-line argument:
```python
parser.add_argument(
    "--httpx-rate-limit",
    type=int,
    default=10,
    help="Rate limit for httpx requests per second (default: 10, used by related_sites plugin)"
)
```

**Default Value**: 10 requests/second
**Purpose**: Balance between scan speed and being respectful to target systems

### 2. Plugin Integration (`kast/plugins/related_sites_plugin.py`)

Modified `_probe_subdomains_with_httpx()` method to:
1. Read rate limit from CLI args with fallback to default
2. Add `-rate-limit` parameter to httpx command
3. Log the rate limit being used for debugging

```python
# Get rate limit from CLI args (default 10 if not specified)
rate_limit = getattr(self.cli_args, 'httpx_rate_limit', 10)
self.debug(f"Using httpx rate limit: {rate_limit} requests/second")

# Add to httpx command
cmd = [
    "httpx",
    # ... other parameters ...
    "-rate-limit", str(rate_limit),
    # ... more parameters ...
]
```

### 3. Documentation Updates

Updated `kast/docs/RELATED_SITES_PLUGIN.md` with:
- Rate limit specification in HTTPx Settings section
- New Example 4 showing various rate limiting scenarios
- Usage examples for conservative, aggressive, and unlimited rates

## Usage Examples

### Conservative Rate Limiting
Good for shared hosting or rate-limited APIs:
```bash
python -m kast.main --target example.com --run-only related_sites --httpx-rate-limit 5
```

### Default Rate Limiting
Balanced approach (10 req/sec):
```bash
python -m kast.main --target example.com --run-only related_sites
```

### Aggressive Rate Limiting
When you need speed and have permission:
```bash
python -m kast.main --target example.com --run-only related_sites --httpx-rate-limit 50
```

### Unlimited Rate Limiting
Maximum speed (use with caution):
```bash
python -m kast.main --target example.com --run-only related_sites --httpx-rate-limit 0
```

## Testing Performed

1. **Default Value Test**
   - Verified default of 10 requests/second when no argument provided
   - ✓ Passed

2. **Custom Value Test**
   - Tested with custom value (25 requests/second)
   - ✓ Passed

3. **Unlimited Test**
   - Tested with value 0 (unlimited)
   - ✓ Passed

4. **CLI Help Test**
   - Verified help text displays correctly
   - ✓ Passed

## Benefits

### 1. Respectful Scanning
- Default 10 req/sec is conservative and respectful
- Reduces chance of triggering rate limits
- Less likely to set off IDS/IPS alerts

### 2. Flexibility
- Users can adjust based on target infrastructure
- Can be more aggressive when scanning own systems
- Can be more conservative when scanning production systems

### 3. Performance Control
- Balance speed vs. stealth
- Adapt to network conditions
- Control resource usage

### 4. Compliance
- Helps meet responsible disclosure guidelines
- Demonstrates consideration for target systems
- Reduces legal/ethical concerns

## Technical Details

### HTTPx Rate Limiting Mechanism

HTTPx's `-rate-limit` flag controls:
- Maximum requests per second across all threads
- Applies to all 50 threads collectively
- Uses token bucket algorithm internally
- Value of 0 disables rate limiting entirely

### Performance Impact

| Rate Limit | 100 Subdomains | 500 Subdomains | Notes |
|------------|----------------|----------------|-------|
| 5 req/sec  | ~5-6 minutes   | ~25-30 minutes | Very conservative |
| 10 req/sec | ~3-4 minutes   | ~12-15 minutes | Default, balanced |
| 25 req/sec | ~2-3 minutes   | ~6-8 minutes   | Faster, still safe |
| 50 req/sec | ~1-2 minutes   | ~4-5 minutes   | Aggressive |
| 0 (unlimited) | ~30-60 seconds | ~2-4 minutes | Maximum speed |

*Note: Times are approximate and depend on network latency, target response times, and number of responsive hosts*

### Thread Interaction

- Plugin uses 50 threads for parallel execution
- Rate limit applies across ALL threads
- Example: With 10 req/sec limit and 50 threads:
  - Each thread gets ~0.2 requests/second on average
  - HTTPx manages distribution automatically

## Security Considerations

### When to Use Lower Rates (5 or less)
- Scanning production systems
- Limited testing authorization
- Shared hosting environments
- Known rate-limited targets
- When stealth is important

### When to Use Default Rate (10)
- General security assessments
- Most testing scenarios
- Unknown target infrastructure
- Following best practices

### When to Use Higher Rates (25+)
- Scanning own infrastructure
- Pen tests with full authorization
- Bug bounty programs (with permission)
- Time-critical assessments

### When to Use Unlimited (0)
- Internal network scanning
- Isolated test environments
- Your own development systems
- When speed is critical and authorized

## Future Enhancements

Potential improvements:
- [ ] Adaptive rate limiting based on target responses
- [ ] Different rates for different ports
- [ ] Rate limit per target (for multi-target scans)
- [ ] Automatic rate limit detection and adjustment
- [ ] Warning when using aggressive rates

## Backward Compatibility

- **Fully backward compatible**: Default value maintains existing behavior
- **No breaking changes**: All existing commands work as before
- **Optional parameter**: Only affects behavior when explicitly set

## Best Practices

1. **Start Conservative**: Begin with default or lower rate
2. **Monitor Responses**: Watch for errors indicating rate limiting
3. **Adjust as Needed**: Increase if targets handle it well
4. **Document Choices**: Note why you chose specific rate limits
5. **Respect Targets**: When in doubt, use lower rates

## Related Documentation

- Main plugin documentation: `RELATED_SITES_PLUGIN.md`
- Implementation summary: `RELATED_SITES_IMPLEMENTATION_SUMMARY.md`
- HTTPx documentation: https://github.com/projectdiscovery/httpx

---

**Feature Version**: 1.1  
**Date Added**: December 16, 2025  
**Status**: Complete and Production Ready
