import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from kast.report_templates import (
    get_talking_point,
    get_severity,
    get_category,
    generate_executive_summary,
    get_issue_metadata
)

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

    for plugin in plugin_results:
        # Normalize plugin name from various possible fields
        tool_name = plugin.get("plugin-name") or plugin.get("tool") or plugin.get("name", "Unknown Tool")
        detailed_results[tool_name] = {
            "summary": format_multiline_text(plugin.get("summary", "")),
            "details": format_multiline_text(plugin.get("details", "")),
            "report": format_multiline_text(plugin.get("report", ""))
        }

        # Handle both string and dict issues
        for issue in plugin.get("issues", []):
            if isinstance(issue, str):
                # Convert string issue to dict format
                issue_dict = {
                    "id": None,
                    "description": issue
                }
            else:
                issue_dict = issue

            issue_id = issue_dict.get("id")
            issue_metadata = get_issue_metadata(issue_id) if issue_id else None
            display_name = issue_metadata.get("display_name") if issue_metadata else None
            all_issues.append({
                "id": issue_id,
                "display_name": display_name,
                "description": issue_dict.get("description", ""),
                "remediation": get_talking_point(issue_id) if issue_id else "No specific remediation available",
                "severity": get_severity(issue_id) if issue_id else "Unknown",
                "category": get_category(issue_id) if issue_id else "Uncategorized"
            })

    # Generate executive summary
    executive_summary = generate_executive_summary(all_issues)

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
        issues=all_issues,
        detailed_results=detailed_results,
        target=target
    )

    # Save to file
    with open(output_path, 'w') as f:
        f.write(html_content)

    print(f"Report saved to {output_path}")
