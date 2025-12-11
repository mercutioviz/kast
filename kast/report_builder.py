import os
import logging
import json
import base64
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
from kast.report_templates import (
    get_talking_point,
    get_severity,
    get_category,
    generate_executive_summary,
    get_issue_metadata
)


# Logger for warnings when registry entries are missing
logger = logging.getLogger(__name__)

def add_word_break_opportunities(text):
    """
    Add word-break opportunities (<wbr> tags) to long strings, especially URLs.
    This helps prevent overflow in PDF rendering.
    HTML-aware: doesn't insert <wbr> inside HTML tags.
    
    Args:
        text (str): The text to process
        
    Returns:
        str: Text with <wbr> tags inserted at appropriate break points
    """
    if not text or len(text) < 80:
        return text
    
    result = []
    inside_tag = False
    i = 0
    
    while i < len(text):
        char = text[i]
        
        # Track if we're inside an HTML tag
        if char == '<':
            inside_tag = True
            result.append(char)
        elif char == '>':
            inside_tag = False
            result.append(char)
        # Only add <wbr> after delimiters if we're NOT inside an HTML tag
        elif not inside_tag and char in ['/', '?', '&', '=', '-', '_', '.', ':', ';', ',']:
            result.append(char)
            result.append('<wbr>')
        else:
            result.append(char)
        
        i += 1
    
    return ''.join(result)

def format_multiline_text(text):
    """
    Converts newline-separated text or lists into HTML paragraphs.
    Handles both string input (split by newlines) and list input.
    Adds word-break opportunities for long strings (like URLs).
    """
    if not text:
        return ""
    
    # Handle list input
    if isinstance(text, list):
        paragraphs = text
    # Handle string input
    else:
        paragraphs = str(text).split('\n')
    
    # Add word-break opportunities to each paragraph to handle long URLs
    formatted_paragraphs = []
    for p in paragraphs:
        if str(p).strip():
            # Add word-break opportunities for long strings
            formatted_p = add_word_break_opportunities(str(p))
            formatted_paragraphs.append(f'<p class="report-paragraph">{formatted_p}</p>')
    
    return '\n'.join(formatted_paragraphs)

def generate_tool_anchor_id(tool_name):
    """
    Generate an anchor ID for a tool section that matches the template format.
    Converts tool name to lowercase and replaces spaces and dots with hyphens.
    """
    return tool_name.lower().replace(' ', '-').replace('.', '-')

def format_multiline_text_as_list(text, tool_name=None):
    """
    Converts newline-separated text or lists into HTML bulleted list.
    Handles both string input (split by newlines) and list input.
    If tool_name is provided, wraps it in an anchor link.
    """
    if not text:
        return ""
    
    # Handle list input
    if isinstance(text, list):
        items = text
    # Handle string input
    else:
        items = str(text).split('\n')
    
    # Filter out empty items
    items = [item for item in items if str(item).strip()]
    
    if not items:
        return ""
    
    # If tool_name is provided, add anchor link to each item
    if tool_name:
        tool_anchor = generate_tool_anchor_id(tool_name)
        formatted_items = []
        for item in items:
            # Wrap the entire item text in an anchor link
            linked_item = f'<a href="#tool-{tool_anchor}" style="color: inherit; text-decoration: underline; cursor: pointer;">{item}</a>'
            formatted_items.append(f'<li>{linked_item}</li>')
        list_items = '\n'.join(formatted_items)
    else:
        list_items = '\n'.join(f'<li>{item}</li>' for item in items)
    
    return f'<ul class="executive-summary-list">\n{list_items}\n</ul>'

# Set up Jinja2 environment
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)

# Load templates
template = env.get_template('report_template.html')
template_pdf = env.get_template('report_template_pdf.html')

def generate_html_report(plugin_results, output_path='kast_report.html', target=None, logo_path=None):
    """
    Generates an HTML report from plugin results using Jinja2.
    
    Args:
        plugin_results (list): List of plugin result dictionaries.
        output_path (str): Path to save the generated HTML report.
        target (str): Target URL/domain being scanned.
        logo_path (str): Optional path to custom logo file (PNG or JPG).
    """
    all_issues = []
    detailed_results = {}
    plugin_executive_summaries = []

    for plugin in plugin_results:
        # Normalize plugin name from various possible fields
        tool_name = plugin.get("plugin-name") or plugin.get("tool") or plugin.get("name", "Unknown Tool")
        # Friendly reporter name: prefer explicit plugin display-name, then plugin description, then tool_name
        reported_by = (
            plugin.get("plugin-display-name")
            or plugin.get("display_name")
            or plugin.get("plugin-description")
            or tool_name
        )
        # Tool display name and purpose for nicer rendering
        display_name = (
            plugin.get("plugin-display-name")
            or plugin.get("display_name")
            or plugin.get("plugin-description")
            or tool_name
        )
        purpose = plugin.get("plugin-description") or plugin.get("description") or ""

        # Collect executive summary if present
        exec_summary = plugin.get("executive_summary", "")
        if exec_summary:
            plugin_executive_summaries.append({
                "plugin_name": display_name,
                "tool_name": tool_name,  # Original tool name for anchor links
                "summary": format_multiline_text_as_list(exec_summary, tool_name)
            })

        # Pass through extra fields for collapsible details
        detailed_results[tool_name] = {
            "display_name": display_name,
            "purpose": purpose,
            "website_url": plugin.get("plugin-website-url"),
            "summary": format_multiline_text(plugin.get("summary", "")),
            "details": format_multiline_text(plugin.get("details", "")),
            "report": format_multiline_text(plugin.get("report", "")),
            "timestamp": plugin.get("timestamp"),
            "disposition": plugin.get("findings", {}).get("disposition") or plugin.get("disposition"),
            "results": plugin.get("findings", {}).get("results") or plugin.get("results"),
            "findings": plugin.get("findings"),
            "custom_html": plugin.get("custom_html", ""),
            "results_message": plugin.get("results_message")  # Custom message for results section
        }

        # Handle both string and dict issues
        for issue in plugin.get("issues", []):
            if isinstance(issue, str):
                # If the plugin returns a simple string issue identifier, use it as the id
                # and also keep the original string as the description for visibility.
                issue_dict = {
                    "id": issue,
                    "description": issue
                }
            else:
                issue_dict = issue

            issue_id = issue_dict.get("id")

            # Normalize issue id (strip whitespace) and ensure it's a string when present
            if isinstance(issue_id, str):
                issue_id = issue_id.strip()

            issue_metadata = get_issue_metadata(issue_id) if issue_id else None

            # If metadata is missing, fall back to showing the raw id as the display name
            if issue_metadata:
                display_name = issue_metadata.get("display_name")
                remediation = get_talking_point(issue_id)
                severity = get_severity(issue_id)
                category = get_category(issue_id)
            else:
                display_name = issue_id
                remediation = "No specific remediation available"
                severity = "Unknown"
                category = "Uncategorized"
                if issue_id:
                    logger.warning(f"Issue ID '{issue_id}' not found in issue registry")

            all_issues.append({
                "id": issue_id,
                "display_name": display_name,
                "reported_by": reported_by,
                "reported_by_tool": tool_name,  # Original tool name for anchor generation
                "description": issue_dict.get("description", ""),
                "remediation": remediation,
                "severity": severity,
                "category": category
            })

    # Define severity order for sorting (highest to lowest)
    severity_order = {"High": 0, "Medium": 1, "Low": 2, "Info": 3, "Unknown": 4}
    
    # Sort issues by severity (highest first)
    all_issues.sort(key=lambda x: severity_order.get(x.get("severity", "Unknown"), 4))
    
    # Generate executive summary
    executive_summary = format_multiline_text_as_list(generate_executive_summary(all_issues))
    
    # Calculate severity counts for badges
    severity_counts = {
        "High": sum(1 for issue in all_issues if issue.get("severity") == "High"),
        "Medium": sum(1 for issue in all_issues if issue.get("severity") == "Medium"),
        "Low": sum(1 for issue in all_issues if issue.get("severity") == "Low"),
        "Info": sum(1 for issue in all_issues if issue.get("severity") == "Info"),
    }
    
    # Prepare metadata for report header
    scan_metadata = {
        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_issues": len(all_issues),
        "total_plugins": len(plugin_results),
        "severity_counts": severity_counts
    }

    # Ensure stylesheet is copied into the output directory so the generated HTML can reference it
    output_dir = os.path.dirname(output_path) or os.getcwd()
    css_src = os.path.join(TEMPLATE_DIR, 'kast_style.css')
    css_dst = os.path.join(output_dir, 'kast_style.css')
    try:
        if os.path.isfile(css_src):
            import shutil
            shutil.copyfile(css_src, css_dst)
    except Exception:
        # Don't fail the whole report generation for CSS copy issues
        pass
    
    # Handle custom logo for HTML report
    logo_filename = None
    if logo_path and os.path.isfile(logo_path):
        try:
            import shutil
            # Copy custom logo to output directory
            logo_filename = os.path.basename(logo_path)
            logo_dst = os.path.join(output_dir, logo_filename)
            shutil.copyfile(logo_path, logo_dst)
            logger.info(f"Custom logo copied to {logo_dst}")
        except Exception as e:
            logger.warning(f"Failed to copy custom logo: {e}. Using default logo.")
            logo_filename = None

    # Render the HTML report
    html_content = template.render(
        executive_summary=executive_summary,
        plugin_executive_summaries=plugin_executive_summaries,
        issues=all_issues,
        detailed_results=detailed_results,
        target=target,
        scan_metadata=scan_metadata,
        custom_logo=logo_filename
    )

    # Save to file
    with open(output_path, 'w') as f:
        f.write(html_content)

    print(f"Report saved to {output_path}")


def image_to_base64(image_path):
    """
    Convert image file to base64 data URI.
    
    Args:
        image_path (str): Path to the image file
        
    Returns:
        str: Base64-encoded data URI or None if file doesn't exist
    """
    try:
        if not os.path.exists(image_path):
            return None
            
        with open(image_path, 'rb') as f:
            data = base64.b64encode(f.read()).decode()
        
        # Determine MIME type from extension
        ext = os.path.splitext(image_path)[1][1:].lower()
        mime_types = {
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'gif': 'image/gif',
            'svg': 'image/svg+xml'
        }
        mime_type = mime_types.get(ext, 'image/png')
        
        return f'data:{mime_type};base64,{data}'
    except Exception as e:
        logger.warning(f"Failed to encode image {image_path}: {e}")
        return None


def format_json_for_pdf(data, max_depth=3, current_depth=0):
    """
    Convert JSON data to formatted HTML for PDF display.
    Limits depth to avoid overly large outputs.
    
    Args:
        data: JSON-serializable data
        max_depth (int): Maximum nesting depth to display (default: 3)
        current_depth (int): Current depth (internal use)
        
    Returns:
        str: Formatted HTML representation
    """
    if data is None:
        return '<span class="json-null">null</span>'
    
    if current_depth >= max_depth:
        return '<span class="json-truncated">[... truncated ...]</span>'
    
    try:
        if isinstance(data, dict):
            if not data:
                return '<span class="json-empty">{}</span>'
            
            items = []
            for key, value in data.items():
                formatted_value = format_json_for_pdf(value, max_depth, current_depth + 1)
                items.append(f'<div class="json-item"><span class="json-key">"{key}":</span> {formatted_value}</div>')
            
            indent = '  ' * current_depth
            return '<div class="json-object">{<div class="json-contents">' + ''.join(items) + '</div>}</div>'
        
        elif isinstance(data, list):
            if not data:
                return '<span class="json-empty">[]</span>'
            
            items = []
            for item in data:
                formatted_item = format_json_for_pdf(item, max_depth, current_depth + 1)
                items.append(f'<div class="json-item">{formatted_item}</div>')
            
            return '<div class="json-array">[<div class="json-contents">' + ''.join(items) + '</div>]</div>'
        
        elif isinstance(data, str):
            # Escape HTML
            escaped = data.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # For very long strings (like URLs), add word-break opportunities
            # Add <wbr> (word break opportunity) tags after common URL delimiters
            if len(escaped) > 80:
                # Add break opportunities after URL-like characters
                for char in ['/', '?', '&', '=', '-', '_', '.', ':', ';', ',']:
                    escaped = escaped.replace(char, char + '<wbr>')
            
            # Still truncate extremely long strings but with higher limit
            if len(escaped) > 500:
                escaped = escaped[:500] + '...'
            
            return f'<span class="json-string">"{escaped}"</span>'
        
        elif isinstance(data, bool):
            return f'<span class="json-boolean">{str(data).lower()}</span>'
        
        elif isinstance(data, (int, float)):
            return f'<span class="json-number">{data}</span>'
        
        else:
            return f'<span class="json-value">{str(data)}</span>'
    
    except Exception as e:
        logger.warning(f"Error formatting JSON for PDF: {e}")
        return f'<pre class="json-display">{json.dumps(data, indent=2)}</pre>'


def generate_pdf_report(plugin_results, output_path='kast_report.pdf', target=None, logo_path=None):
    """
    Generates a PDF report from plugin results using WeasyPrint.
    
    Args:
        plugin_results (list): List of plugin result dictionaries.
        output_path (str): Path to save the generated PDF report.
        target (str): Target URL/domain being scanned.
        logo_path (str): Optional path to custom logo file (PNG or JPG).
    """
    try:
        from weasyprint import HTML, CSS
        from weasyprint.text.fonts import FontConfiguration
    except ImportError:
        print("Error: WeasyPrint is not installed. Install it with: pip install weasyprint")
        print("Note: WeasyPrint may require additional system dependencies.")
        return
    
    # Prepare data similar to HTML report
    all_issues = []
    detailed_results = {}
    plugin_executive_summaries = []

    for plugin in plugin_results:
        # Normalize plugin name from various possible fields
        tool_name = plugin.get("plugin-name") or plugin.get("tool") or plugin.get("name", "Unknown Tool")
        # Friendly reporter name
        reported_by = (
            plugin.get("plugin-display-name")
            or plugin.get("display_name")
            or plugin.get("plugin-description")
            or tool_name
        )
        # Tool display name and purpose
        display_name = (
            plugin.get("plugin-display-name")
            or plugin.get("display_name")
            or plugin.get("plugin-description")
            or tool_name
        )
        purpose = plugin.get("plugin-description") or plugin.get("description") or ""

        # Collect executive summary
        exec_summary = plugin.get("executive_summary", "")
        if exec_summary:
            plugin_executive_summaries.append({
                "plugin_name": display_name,
                "tool_name": tool_name,  # Original tool name for anchor links
                "summary": format_multiline_text_as_list(exec_summary)
            })

        # For PDF, pre-render JSON structures
        results_data = plugin.get("findings", {}).get("results") or plugin.get("results")
        results_html = ""
        if results_data:
            results_html = format_json_for_pdf(results_data)

        # Use PDF-specific custom HTML if available, otherwise fall back to regular custom HTML
        custom_html_for_pdf = plugin.get("custom_html_pdf") or plugin.get("custom_html", "")
        
        # Pass through fields for detailed results
        detailed_results[tool_name] = {
            "display_name": display_name,
            "purpose": purpose,
            "website_url": plugin.get("plugin-website-url"),
            "summary": format_multiline_text(plugin.get("summary", "")),
            "details": format_multiline_text(plugin.get("details", "")),
            "report": format_multiline_text(plugin.get("report", "")),
            "timestamp": plugin.get("timestamp"),
            "disposition": plugin.get("findings", {}).get("disposition") or plugin.get("disposition"),
            "results": None,  # Set to None for PDF mode to avoid JSON serialization issues
            "results_html": results_html,  # Pre-rendered for PDF
            "findings": plugin.get("findings"),
            "findings_json": json.dumps(plugin.get("findings"), indent=2) if plugin.get("findings") else "",
            "custom_html": custom_html_for_pdf,  # Use PDF version for PDF reports
            "results_message": plugin.get("results_message")  # Custom message for results section
        }

        # Handle issues
        for issue in plugin.get("issues", []):
            if isinstance(issue, str):
                issue_dict = {"id": issue, "description": issue}
            else:
                issue_dict = issue

            issue_id = issue_dict.get("id")
            if isinstance(issue_id, str):
                issue_id = issue_id.strip()

            issue_metadata = get_issue_metadata(issue_id) if issue_id else None

            if issue_metadata:
                display_name = issue_metadata.get("display_name")
                remediation = get_talking_point(issue_id)
                severity = get_severity(issue_id)
                category = get_category(issue_id)
            else:
                display_name = issue_id
                remediation = "No specific remediation available"
                severity = "Unknown"
                category = "Uncategorized"
                if issue_id:
                    logger.warning(f"Issue ID '{issue_id}' not found in issue registry")

            all_issues.append({
                "id": issue_id,
                "display_name": display_name,
                "reported_by": reported_by,
                "reported_by_tool": tool_name,  # Original tool name for anchor generation
                "description": issue_dict.get("description", ""),
                "remediation": remediation,
                "severity": severity,
                "category": category
            })

    # Sort issues by severity
    severity_order = {"High": 0, "Medium": 1, "Low": 2, "Info": 3, "Unknown": 4}
    all_issues.sort(key=lambda x: severity_order.get(x.get("severity", "Unknown"), 4))
    
    # Generate executive summary
    executive_summary = format_multiline_text_as_list(generate_executive_summary(all_issues))
    
    # Calculate severity counts
    severity_counts = {
        "High": sum(1 for issue in all_issues if issue.get("severity") == "High"),
        "Medium": sum(1 for issue in all_issues if issue.get("severity") == "Medium"),
        "Low": sum(1 for issue in all_issues if issue.get("severity") == "Low"),
        "Info": sum(1 for issue in all_issues if issue.get("severity") == "Info"),
    }
    
    # Prepare metadata
    scan_metadata = {
        "scan_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_issues": len(all_issues),
        "total_plugins": len(plugin_results),
        "severity_counts": severity_counts
    }

    # Convert images to base64 for embedding
    # Use custom logo if provided, otherwise use default
    if logo_path and os.path.isfile(logo_path):
        logo_base64 = image_to_base64(logo_path)
        if not logo_base64:
            # If custom logo fails to encode, fall back to default
            logger.warning(f"Failed to encode custom logo: {logo_path}. Using default logo.")
            assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
            default_logo = os.path.join(assets_dir, 'kast-logo.png')
            logo_base64 = image_to_base64(default_logo)
    else:
        # Use default logo
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets')
        default_logo = os.path.join(assets_dir, 'kast-logo.png')
        logo_base64 = image_to_base64(default_logo)

    # Render HTML content using PDF-specific template
    html_content = template_pdf.render(
        executive_summary=executive_summary,
        plugin_executive_summaries=plugin_executive_summaries,
        issues=all_issues,
        detailed_results=detailed_results,
        target=target,
        scan_metadata=scan_metadata,
        logo_base64=logo_base64
    )

    # Set up base URL for resolving relative paths
    base_url = f'file://{os.path.abspath(TEMPLATE_DIR)}/'
    
    # Configure fonts for proper rendering
    font_config = FontConfiguration()
    
    # Load PDF-specific CSS with absolute path
    css_path = os.path.join(TEMPLATE_DIR, 'kast_style_pdf.css')
    css = CSS(filename=css_path, font_config=font_config)
    
    # Generate PDF
    try:
        html_obj = HTML(string=html_content, base_url=base_url)
        html_obj.write_pdf(output_path, stylesheets=[css], font_config=font_config)
        print(f"PDF report saved to {output_path}")
    except Exception as e:
        print(f"Error generating PDF: {e}")
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise
