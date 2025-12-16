# Related Sites Discovery Plugin

## Overview

The Related Sites Discovery plugin is a comprehensive tool-chaining plugin that combines subdomain enumeration with HTTP probing to identify and catalog related web properties for a given target domain.

## Features

- **Apex Domain Extraction**: Automatically identifies and scans the apex domain from any FQDN
- **Subdomain Discovery**: Uses subfinder to enumerate subdomains
- **HTTP Probing**: Probes discovered subdomains with httpx to identify live web services
- **Rich Categorization**: Groups results by status code, port, technology, CDN, WebSocket support
- **Interactive Reports**: Custom HTML widgets with collapsible sections and statistics
- **PDF-Friendly Output**: Simplified, truncated views for PDF reports

## How It Works

### Workflow

1. **Extract Apex Domain**: From `www.example.com` → `example.com`
2. **Subdomain Discovery**: Run subfinder on apex domain
3. **HTTP Probing**: Test each discovered subdomain with httpx on common web ports
4. **Categorization**: Group results by various attributes
5. **Report Generation**: Create interactive visualizations

### Architecture

This plugin uses the **standalone mode** approach:
- Self-contained execution (no dependencies on other plugins)
- Direct subprocess calls to subfinder and httpx
- Complete control over tool parameters and workflow
- Parallel httpx execution for efficiency (50 threads)

## Requirements

### CLI Tools
- `subfinder` - Subdomain enumeration
- `httpx` - HTTP probing and technology detection

### Python Dependencies
- `tldextract>=3.4.0` - Robust apex domain extraction

## Configuration

### Plugin Properties
- **Name**: `related_sites`
- **Display Name**: Related Sites Discovery
- **Priority**: 45 (runs after initial recon, before deep analysis)
- **Scan Type**: Passive (makes HTTP requests to discovered hosts)
- **Output Type**: File-based

### HTTPx Settings
- **Ports**: 80, 443, 8080, 8443, 8000, 8888
- **Timeout**: 10 seconds per host
- **Retries**: 2
- **Threads**: 50 (parallel execution)
- **Rate Limit**: 10 requests/second (default, configurable via CLI)
- **Features**: Follow redirects, tech detection, CDN detection, WebSocket support

### Subfinder Settings
- **Timeout**: 5 minutes
- **Output Format**: JSON Lines
- **Mode**: Silent (unless verbose flag is enabled)

## Usage

### Basic Scan
```bash
# Run only the related sites plugin
python -m kast.main --target example.com --run-only related_sites

# Run with verbose output
python -m kast.main --target example.com --run-only related_sites --verbose

# Include in full scan
python -m kast.main --target example.com
```

### Target Behavior
- If target is a subdomain (e.g., `www.example.com`), the plugin will scan the apex domain (`example.com`)
- If target is already an apex domain (e.g., `example.com`), it will scan that domain
- This ensures comprehensive subdomain discovery across the entire domain

## Output

### Raw Output (`related_sites.json`)
```json
{
  "target": "www.example.com",
  "apex_domain": "example.com",
  "scanned_domain": "example.com",
  "total_subdomains": 42,
  "subdomains": ["sub1.example.com", "sub2.example.com", ...],
  "live_hosts": [...],
  "dead_hosts": [...],
  "by_status": {
    "200": [...],
    "301": [...],
    "404": [...]
  },
  "by_port": {
    "80": [...],
    "443": [...]
  },
  "technologies": {
    "nginx": [...],
    "cloudflare": [...]
  },
  "redirects": [...],
  "with_cdn": [...],
  "websockets": [...],
  "statistics": {
    "total_discovered": 42,
    "total_live": 28,
    "total_dead": 14,
    "response_rate": 66.7,
    "unique_technologies": 5,
    "cdn_protected": 12,
    "websocket_enabled": 2,
    "redirects_count": 8
  }
}
```

### Processed Output (`related_sites_processed.json`)
Includes:
- Plugin metadata
- Executive summary (high-level findings)
- Detailed statistics
- Custom HTML widgets for report display
- PDF-friendly simplified output

### Report Features

#### HTML Report
- **Statistics Cards**: Visual display of key metrics
- **Collapsible Groups**: Hosts organized by status code
- **Clickable URLs**: Direct links to discovered hosts
- **Technology Tags**: Shows detected technologies per host
- **CDN Indicators**: Highlights CDN-protected hosts

#### PDF Report
- **Truncated Lists**: Shows top 25 hosts to keep PDF concise
- **Summary Statistics**: Key metrics at a glance
- **Note**: Links users to full HTML report for complete data

## Implementation Details

### Apex Domain Extraction
Uses `tldextract` library for robust parsing that handles:
- Multi-part TLDs (e.g., `.co.uk`, `.gov.au`)
- International domains
- Edge cases in domain structure

Falls back to simple heuristic if tldextract unavailable.

### Parallel Execution
- HTTPx runs with 50 parallel threads for efficiency
- Subfinder runs with single process (already optimized internally)
- Total execution time scales with number of subdomains

### Error Handling
- Subfinder timeout: 5 minutes
- HTTPx timeout: 10 minutes
- Graceful handling of partial results
- Continues even if some tools fail

### Report-Only Mode
Supports regenerating reports from existing results without re-scanning:
```bash
python -m kast.main --report-only ~/kast_results/example.com-20251216-220000/
```

## Performance Considerations

### Typical Execution Times
- Small domain (< 10 subdomains): 1-2 minutes
- Medium domain (10-50 subdomains): 2-5 minutes
- Large domain (50-200 subdomains): 5-15 minutes
- Very large domain (200+ subdomains): 15+ minutes

### Resource Usage
- **CPU**: Moderate (parallel HTTP requests)
- **Memory**: Low (streaming JSON processing)
- **Network**: High (many HTTP requests)
- **Disk**: Low (JSON output only)

## Troubleshooting

### No Subdomains Found
- Verify subfinder is installed: `which subfinder`
- Check domain is valid and has subdomains
- Try running subfinder manually: `subfinder -d example.com`

### HTTPx Timeouts
- Some hosts may be slow or unreachable
- Plugin continues with partial results
- Check network connectivity
- Consider firewall/rate limiting issues

### Missing Dependencies
Install required tools:
```bash
# Install subfinder
go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest

# Install httpx
go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest

# Install Python dependency
pip install tldextract
```

## Integration with Other Plugins

### Execution Order
The plugin runs at **priority 45**, which means:
- **Before**: Deep analysis plugins (katana, etc.)
- **After**: Basic infrastructure detection (Observatory, WhatWeb)

### Complementary Plugins
- **Subfinder Plugin**: May provide overlapping data, but this plugin adds HTTP probing
- **Katana Plugin**: Can crawl the discovered live hosts
- **WhatWeb Plugin**: Technology detection complements httpx tech detection

## Future Enhancements

Potential improvements:
- [ ] Configurable port lists via CLI arguments
- [ ] Configurable thread count for httpx
- [ ] Subdomain filtering (skip certain patterns)
- [ ] Integration with cloud providers for distributed scanning
- [ ] DNS record enrichment (A, AAAA, CNAME, MX records)
- [ ] Screenshot capture of live hosts
- [ ] Vulnerability correlation with discovered services

## Examples

### Example 1: Basic Discovery
```bash
python -m kast.main --target example.com --run-only related_sites
```
Output: Discovers all subdomains and probes for live hosts

### Example 2: Verbose Mode
```bash
python -m kast.main --target www.example.com --run-only related_sites --verbose
```
Output: Shows detailed debug information about subfinder/httpx execution

### Example 3: Full Scan
```bash
python -m kast.main --target example.com
```
Output: Includes related_sites along with all other plugins

### Example 4: Custom Rate Limiting
```bash
# Conservative rate limiting (5 requests/second)
python -m kast.main --target example.com --run-only related_sites --httpx-rate-limit 5

# Aggressive rate limiting (50 requests/second)
python -m kast.main --target example.com --run-only related_sites --httpx-rate-limit 50

# No rate limiting (0 = unlimited)
python -m kast.main --target example.com --run-only related_sites --httpx-rate-limit 0
```
Output: Adjusts httpx request rate to avoid overwhelming targets or triggering rate limits

## Security Considerations

### Active Scanning
This plugin performs **active scanning** by making HTTP requests to discovered hosts. Consider:
- Obtain permission before scanning
- May trigger IDS/IPS alerts
- Respect rate limiting
- Some hosts may log access attempts

### Data Sensitivity
- Discovered subdomains may reveal infrastructure details
- Technology detection may identify vulnerable versions
- Store scan results securely
- Follow responsible disclosure practices

## References

- [Subfinder Documentation](https://github.com/projectdiscovery/subfinder)
- [HTTPx Documentation](https://github.com/projectdiscovery/httpx)
- [tldextract Library](https://github.com/john-kurkowski/tldextract)

---

**Version**: 1.0  
**Date**: December 2025  
**Author**: KAST Development Team
