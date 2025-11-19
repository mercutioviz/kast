import os
import logging
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

def format_multiline_text(text):
    """
    Converts newline-separated text or lists into HTML paragraphs.
    Handles both string input (split by newlines) and list input.
    """
    if not text:
        return ""
    
    # Handle list input
    if isinstance(text, list):
        paragraphs = text
    # Handle string input
    else:
        paragraphs = str(text).split('\n')
    
    return '\n'.join(f'<p class="report-paragraph">{p}</p>' for p in paragraphs if str(p).strip())

def format_multiline_text_as_list(text):
    """
    Converts newline-separated text or lists into HTML bulleted list.
    Handles both string input (split by newlines) and list input.
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
    
    list_items = '\n'.join(f'<li>{item}</li>' for item in items)
    return f'<ul class="executive-summary-list">\n{list_items}\n</ul>'

# Set up Jinja2 environment
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)

# Load the HTML template
template = env.get_template('report_template.html')

def generate_html_report(plugin_results, output_path='kast_report.html', target=None):
    """
    Generates an HTML report from plugin results using Jinja2.
    
    Args:
        plugin_results (list): List of plugin result dictionaries.
        output_path (str): Path to save the generated HTML report.
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
                "summary": format_multiline_text_as_list(exec_summary)
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
            "custom_html": plugin.get("custom_html", "")
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

    # Render the HTML report
    html_content = template.render(
        executive_summary=executive_summary,
        plugin_executive_summaries=plugin_executive_summaries,
        issues=all_issues,
        detailed_results=detailed_results,
        target=target,
        scan_metadata=scan_metadata
    )

    # Save to file
    with open(output_path, 'w') as f:
        f.write(html_content)

    print(f"Report saved to {output_path}")
