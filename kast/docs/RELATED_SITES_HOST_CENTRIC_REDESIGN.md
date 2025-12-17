# Related Sites Plugin - Host-Centric Redesign

## Implementation Date
December 16, 2025

## Overview

Completely redesigned the Related Sites plugin to use a host-centric approach where statistics and display are organized by unique subdomains rather than individual port responses.

## The Problem

### Original (Incorrect) Behavior
- **Counted port responses as "hosts"**: Each HTTP response was counted separately
- **Example**: 4 subdomains × 2 ports = 8 "live hosts" ❌
- **Confusing statistics**: Live hosts (8) + Dead hosts (12) ≠ Total subdomains (16)
- **Mixed terminology**: "Live hosts" counted responses, "dead hosts" counted subdomains

### User Requirements
A "host" should mean a "subdomain":
- A host is **alive** if it responds on ANY tested port
- A host is **dead** if it doesn't respond on ANY tested port
- Statistics should show: 4 live hosts (25%), 12 dead hosts (75%)
- Display should group by subdomain with port details beneath

## Solution Implemented

### 1. Core Data Structure Changes

**Old Structure (Port-Centric)**
```python
{
    "live_hosts": [
        {"url": "https://example.com:443", "host": "example.com", "port": 443},
        {"url": "http://example.com:80", "host": "example.com", "port": 80},
        # Each port response listed separately
    ],
    "dead_hosts": ["subdomain1.com", "subdomain2.com"]
}
```

**New Structure (Host-Centric)**
```python
{
    "live_hosts": [
        {
            "host": "example.com",
            "ports": [80, 443],
            "port_responses": [
                {
                    "port": 443,
                    "url": "https://example.com:443",
                    "status_code": 200,
                    "title": "Example",
                    "technologies": ["Apache"],
                    "cdn": "",
                    "websocket": False
                },
                {
                    "port": 80,
                    # ... similar structure
                }
            ],
            "technologies": ["Apache"],  # Aggregated across all ports
            "has_cdn": False,
            "has_websocket": False
        }
    ],
    "dead_hosts": ["subdomain1.com", "subdomain2.com"]
}
```

### 2. Modified Methods

#### `_parse_httpx_results()` - Complete Rewrite
**Purpose**: Aggregate HTTPx responses by host instead of storing individual responses

**Key Changes**:
- Groups all port responses by hostname
- Builds host-centric data structure with per-port details
- Returns unique live hosts count
- Properly identifies dead hosts (no response on any port)

**Before**:
```python
# Counted each response
live_hosts_set.add(host)
results["live_hosts"].append(host_info)  # One per port
```

**After**:
```python
# Aggregate by host
if host not in hosts_data:
    hosts_data[host] = []
hosts_data[host].append(port_response)

# Then build host-centric list
for host, port_responses in hosts_data.items():
    host_info = {
        "host": host,
        "ports": sorted(unique_ports),
        "port_responses": port_responses,
        # ... aggregated data
    }
```

#### `run()` - Updated Statistics Calculation
**Changes**:
- Removed old categorizations (by_status, by_port, etc.)
- Calculate statistics from host-centric data
- Aggregate technologies across all hosts
- Count CDN/WebSocket by unique hosts, not responses

#### `_generate_executive_summary()` - Host-Centric Metrics
**Changes**:
- Count unique live hosts, not port responses
- Iterate through hosts to count status codes
- Technology counts represent unique hosts using them

#### `_generate_custom_html()` - Complete Redesign
**Features**:
- **Expandable Sections**: Separate sections for live and dead hosts
- **Pagination**: Show 25/50/100/All hosts
- **Host-Centric Display**: Group by subdomain with port details
- **Per-Port Details**: Show status, title, technologies for each port
- **Responsive Design**: Works on various screen sizes

**Structure**:
```html
▼ Live Hosts (4)
  bank.darklab.cudalabx.net
    Ports: 80, 443
    Port 80: Status 200, Technologies: Bootstrap, jQuery
    Port 443: Status 200, Technologies: Bootstrap, jQuery
  [Show 25] [Show 50] [Show All]

▼ Dead Hosts (12)
  insight01.cudalabx.net
  insight02.cudalabx.net
  ...
  [Show 25] [Show 50] [Show All]
```

#### `_generate_pdf_html()` - Simplified Table View
**Features**:
- Host-centric table with Host, Ports, Technologies columns
- Per-port technology breakdown
- Top 25 live hosts detailed
- Dead hosts summary (up to 50 listed)

## Verification Results

### Test Scan: waas.cudalabx.net

**Before Fix**:
```
Total Subdomains: 16
Live Hosts: 8 (50% response rate)
Dead Hosts: 12
```

**After Fix**:
```
Total Subdomains: 16
Live Hosts: 4 (25% response rate)
Dead Hosts: 12

Live Host Breakdown:
1. bank.darklab.cudalabx.net - Ports: [80, 443]
2. sbs.cudalabx.net - Ports: [80, 443]
3. waas.cudalabx.net - Ports: [80, 443]
4. www.darklab.cudalabx.net - Ports: [80, 443]
```

**Verification**: ✓ 4 unique hosts + 12 dead = 16 total subdomains

## Files Modified

1. **kast/plugins/related_sites_plugin.py**
   - `_parse_httpx_results()` - Lines ~308-391 (complete rewrite)
   - `run()` - Lines ~425-445 (statistics calculation)
   - `_generate_executive_summary()` - Lines ~527-572 (host-centric counts)
   - `_generate_custom_html()` - Lines ~620-883 (complete redesign)
   - `_generate_pdf_html()` - Lines ~885-937 (host-centric table)

## User Interface Changes

### HTML Report
- **Statistics Cards**: Show correct host counts with percentages
- **Expandable Sections**: Click to expand/collapse live and dead hosts
- **Pagination Controls**: Buttons to adjust page size
- **Host Cards**: Beautiful card design for each host
- **Port Details**: Nested display showing status, title, tech per port
- **Responsive Grid**: Dead hosts display in auto-fitting grid

### PDF Report
- **Clean Table**: Host, Ports, Technologies columns
- **Per-Port Breakdown**: Technologies listed per port
- **Manageable Size**: Top 25 live hosts, first 50 dead hosts
- **Full Report Link**: Prompts to view HTML for complete data

## Benefits

### 1. Accurate Statistics
- Host counts match intuitive understanding
- Percentages correctly represent subdomain discovery
- Math adds up: live + dead = total

### 2. Clearer Communication
- Executive summary speaks in terms of "subdomains"
- No confusion about what a "host" means
- Response rate meaningful: 25% of subdomains responding

### 3. Better Organization
- Group related data (same host, different ports) together
- Easy to see which hosts are multi-port
- Technologies aggregated per host, not duplicated

### 4. Scalability
- Pagination handles hundreds of hosts
- Expandable sections reduce initial load
- Show 25/50/100/All options give control

### 5. Better User Experience
- Intuitive navigation
- Quick overview with drill-down capability
- Consistent terminology throughout

## Implementation Notes

### JavaScript Features
- **State Management**: Separate state for live and dead hosts pagination
- **Dynamic Rendering**: JavaScript generates HTML from JSON data
- **Interactive Controls**: Click handlers for expansion and pagination
- **Page Navigation**: Previous/Next buttons when needed

### CSS Styling
- **Color-Coded Status**: Green for success, yellow for redirect, red for error
- **Gradient Cards**: Professional stat cards with gradients
- **Responsive Grid**: Auto-fitting columns for dead hosts
- **Hover Effects**: Interactive feedback on clickable elements

### Data Flow
```
HTTPx JSON Output
    ↓
Parse & Group by Host (_parse_httpx_results)
    ↓
Host-Centric Data Structure
    ↓
Statistics Calculation (run)
    ↓
Post-Processing (post_process)
    ↓
HTML Generation (_generate_custom_html)
    ↓
Final Report
```

## Testing Performed

1. ✅ **New Scan**: Verified correct statistics from fresh scan
2. ✅ **Statistics**: 4 live (25%) + 12 dead (75%) = 16 total
3. ✅ **Live Hosts**: Each shows multiple ports correctly
4. ✅ **Port Details**: Technologies and status per port
5. ✅ **Pagination**: All page sizes work (25/50/100/All)
6. ✅ **Expansion**: Sections expand/collapse properly
7. ✅ **PDF Output**: Table displays correctly
8. ✅ **Executive Summary**: Accurate high-level metrics

## Backward Compatibility

**Breaking Change**: Yes - data structure has changed

**Migration**: Old scan data will need to be re-scanned to use new structure

**Justification**: The old structure was fundamentally incorrect and misleading

## Related Documentation

- Main Plugin Docs: `RELATED_SITES_PLUGIN.md`
- Implementation Summary: `RELATED_SITES_IMPLEMENTATION_SUMMARY.md`
- Rate Limiting: `RELATED_SITES_RATE_LIMITING.md`
- Post-Processing Bug Fix: `RELATED_SITES_POSTPROCESSING_BUG_FIX.md`

---

**Status**: Complete  
**Version**: 2.0  
**Date**: December 16, 2025
