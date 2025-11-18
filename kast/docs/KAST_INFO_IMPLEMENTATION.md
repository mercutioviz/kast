# Options for Adding "Download as PDF" to Kast Report

## 1. Python Libraries for HTML to PDF Conversion

- **WeasyPrint**: Pure Python, supports modern CSS, easy to use for HTML templates.
- **pdfkit + wkhtmltopdf**: Uses wkhtmltopdf binary, good for complex HTML/CSS, requires external dependency.
- **xhtml2pdf**: Python-only, but limited CSS support.
- **ReportLab**: Powerful, but requires manual PDF layout (not HTML-based).

## 2. Integration Approaches

- **CLI Option**: Add a command-line flag to generate PDF after HTML report is built.
- **Web UI Button**: If Kast has a web interface, add a "Download as PDF" button that triggers PDF generation.
- **Automated Export**: Automatically generate PDF alongside HTML in the report builder.

## 3. Implementation Steps

- Install and test chosen library (e.g., pip install weasyprint).
- Update report builder to generate PDF from HTML output.
- Add CLI flag or UI button for PDF export.
- Test PDF output for formatting and completeness.

## 4. Example (WeasyPrint)

```python
import weasyprint

def html_to_pdf(html_path, pdf_path):
    weasyprint.HTML(html_path).write_pdf(pdf_path)
```

## 5. Considerations

- CSS compatibility (WeasyPrint is best for modern CSS).
- External dependencies (pdfkit requires wkhtmltopdf).
- Output quality and fidelity.
