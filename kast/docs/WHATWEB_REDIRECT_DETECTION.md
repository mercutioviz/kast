# WhatWeb Domain Redirect Detection Feature

## Overview
Added functionality to the WhatWeb plugin to detect when a redirect changes the domain name and automatically generate recommendations in the executive summary.

## Implementation Details

### Changes Made to `kast/plugins/whatweb_plugin.py`

1. **Added `_detect_domain_redirects()` method**:
   - Detects HTTP 301 and 302 redirects that change the domain name
   - Ignores protocol-only redirects (e.g., http → https on same domain)
   - Prevents duplicate recommendations using a seen_redirects set
   - Returns a list of recommendation strings

2. **Updated `post_process()` method**:
   - Calls `_detect_domain_redirects()` to analyze findings
   - Populates the `executive_summary` field with recommendations
   - Properly structures findings for report generation

### How It Works

The plugin analyzes WhatWeb results looking for:
- Entries with HTTP status 301 or 302
- RedirectLocation plugin data
- Domain name changes between target and redirect location

When a domain change is detected, it generates a recommendation like:
```
Recommend running a scan on www.sanger.k12.ca.us, which was the target redirection location from sanger.k12.ca.us
```

### Example Use Case

Given the WhatWeb results for `sanger.k12.ca.us`:
1. `http://sanger.k12.ca.us` → 301 redirect to `https://www.sanger.k12.ca.us/`
2. `https://sanger.k12.ca.us` → 301 redirect to `https://www.sanger.k12.ca.us/`
3. `https://www.sanger.k12.ca.us/` → 200 OK

The plugin:
- Ignores the first redirect (same domain, just protocol change)
- Detects the second redirect (domain change from `sanger.k12.ca.us` to `www.sanger.k12.ca.us`)
- Generates one recommendation for the domain change
- Adds it to the executive summary section of the report

## Testing

Three test scripts were created to verify the functionality:

1. **test_whatweb_redirect.py**: Unit test for the redirect detection logic
2. **test_whatweb_full_integration.py**: Full integration test with HTML report generation
3. Both tests confirm the recommendation appears correctly in the executive summary

All tests passed successfully.

## Benefits

- Automatically identifies when a target redirects to a different domain
- Provides actionable recommendations in the executive summary
- Helps ensure comprehensive scanning coverage
- Reduces manual analysis needed to identify additional scan targets

## Additional Improvements to Report Format

### Bulleted Lists in Executive Summary

Modified the report builder to display "Scan Findings" and "Potential Issues" sections as bulleted lists instead of simple paragraph elements:

**Changes to `kast/report_builder.py`**:
- Added `format_multiline_text_as_list()` function to convert text into HTML `<ul>` and `<li>` elements
- Updated executive summary formatting to use bulleted lists
- Both plugin executive summaries and general executive summaries now display as lists

**Changes to `kast/templates/kast_style.css`**:
- Added `.executive-summary-list` class styling
- Added `.executive-summary-list li` styling for proper spacing and appearance

**Result**: Executive summary sections now display as clean, easy-to-read bulleted lists, improving report readability and professional appearance.
