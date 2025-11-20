# PDF Report Generation

## Overview

KAST now supports generating PDF versions of security scan reports using WeasyPrint. This feature provides a professional, printable format suitable for sharing with stakeholders or archiving.

## Installation

The PDF generation feature requires WeasyPrint and its dependencies:

```bash
pip install -r requirements.txt
```

**Note:** WeasyPrint may require additional system dependencies depending on your platform:
- **Linux (Debian/Ubuntu):** `sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0`
- **Linux (Fedora):** `sudo dnf install pango`
- **macOS:** WeasyPrint dependencies are typically included with Python installations

## Usage

### Command Line Options

Use the `--format` option to specify the output format:

```bash
# Generate HTML report only (default)
python -m kast.main -t example.com

# Generate PDF report only
python -m kast.main -t example.com --format pdf

# Generate both HTML and PDF reports
python -m kast.main -t example.com --format both
```

### Report-Only Mode

The PDF generation feature works seamlessly with `--report-only` mode:

```bash
# Generate PDF from existing scan results
python -m kast.main --report-only /path/to/scan/results --format pdf

# Generate both formats from existing results
python -m kast.main --report-only /path/to/scan/results --format both
```

## Features

### PDF-Specific Optimizations

1. **Base64-Embedded Images:** Logo images are embedded directly in the PDF, eliminating external dependencies
2. **Static Content:** Interactive elements (JavaScript, collapsible sections) are expanded and rendered statically
3. **Pre-rendered JSON:** Complex JSON structures are formatted as readable HTML instead of interactive tree views
4. **Print-Optimized CSS:** Special styling for better pagination and readability
5. **Page Break Control:** Intelligent page breaks prevent splitting of issues or tool sections

### Preserved Elements

- Full color styling and branding
- Severity badges with counts
- Executive summary
- All issues with severity classifications
- Complete tool results and findings
- Footer with generation timestamp

### PDF-Specific Rendering

**JSON Display:**
- Interactive JSON trees are converted to formatted, indented HTML
- Depth limited to 5 levels to prevent excessive output
- Long strings are truncated for readability

**Collapsible Sections:**
- All details are expanded and visible by default
- Toggle buttons are hidden in PDF output

**Images:**
- KAST logo is embedded as base64 in both header and footer
- No external image dependencies

## Technical Implementation

### Architecture

The PDF generation uses a **separate template approach** for optimal results:

1. **Shared Data Pipeline:** Both HTML and PDF reports use the same data preparation logic
2. **Dedicated Templates:** 
   - `report_template.html` - Interactive HTML with JavaScript, collapsible sections
   - `report_template_pdf.html` - Static, print-optimized layout
3. **Separate Stylesheets:**
   - `kast_style.css` - Web-optimized styling for HTML
   - `kast_style_pdf.css` - Print-optimized styling for PDF
4. **WeasyPrint Rendering:** PDF template is converted to PDF using WeasyPrint's CSS3 rendering engine

### Key Components

**report_builder.py:**
- `generate_html_report()` - Generates interactive HTML reports
- `generate_pdf_report()` - Generates print-optimized PDF reports
- `format_json_for_pdf()` - Converts JSON to formatted HTML (5-level depth)
- `image_to_base64()` - Embeds images as data URIs

**Templates:**
- `report_template.html` - Interactive web report with JavaScript
- `report_template_pdf.html` - Static PDF report with cover page

**Stylesheets:**
- `kast_style.css` - Web styling with interactive elements
- `kast_style_pdf.css` - Print styling with page controls and professional layout

## Performance Considerations

- PDF generation typically takes 2-5 seconds for standard reports
- Large reports (>100 issues) may take longer
- Memory usage is proportional to report size
- JSON structures are depth-limited to avoid excessive output

## Troubleshooting

### WeasyPrint Not Found

If you see "Error: WeasyPrint is not installed":
```bash
pip install weasyprint
```

### Missing System Dependencies

If WeasyPrint fails to import, install system dependencies:
```bash
# Debian/Ubuntu
sudo apt-get install libpango-1.0-0 libpangocairo-1.0-0

# Fedora
sudo dnf install pango
```

### CSS Property Warnings

WeasyPrint may display warnings about unsupported CSS properties:
- `box-shadow` - Visual effects not supported in PDF rendering
- `filter` / `backdrop-filter` - Advanced visual effects ignored
- `print-color-adjust` / `color-adjust` - Non-standard properties

These warnings are **normal and safe to ignore**. They don't affect PDF generation, only inform you that certain visual effects (shadows, filters) won't appear in the PDF. All essential content and colors are preserved.

### Font/Emoji Issues

If emojis don't render correctly in the PDF:
- Install system fonts that include emoji support
- Consider using the HTML report for best emoji rendering

### Large File Sizes

If PDF files are too large:
- Background images are not included in PDFs
- Logo images are base64-encoded (adds ~50KB)
- Consider HTML format for very large reports

## Limitations

1. **No Interactive Elements:** PDFs are static documents
2. **Limited JSON Depth:** JSON structures are truncated at 5 levels
3. **No Tree Navigation:** JSON trees cannot be collapsed/expanded
4. **Font Limitations:** Emoji rendering depends on system fonts
5. **File Size:** PDFs are larger than HTML due to embedded content

## Future Enhancements

Potential improvements for future versions:

- Configurable JSON depth limit
- Optional table of contents with page numbers
- Watermark support for draft reports
- Custom page headers/footers
- Multiple page size options (Letter, A4, etc.)
- Report compression options

## Examples

### Basic Usage

```bash
# Standard scan with PDF output
python -m kast.main -t example.com --format pdf

# Scan with both formats
python -m kast.main -t example.com --format both -o ./scan_results
```

### Advanced Usage

```bash
# Report-only mode with PDF
python -m kast.main --report-only ~/kast_results/example.com-20231119/ --format pdf

# Parallel scan with PDF output
python -m kast.main -t example.com -p --max-workers 10 --format both
```

## Support

For issues or questions about PDF generation:
1. Check WeasyPrint installation and dependencies
2. Review log files in `/var/log/kast/`
3. Verify system has required fonts and libraries
4. Test with HTML format first to isolate PDF-specific issues
