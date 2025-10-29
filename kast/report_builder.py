import os
from jinja2 import Environment, FileSystemLoader, select_autoescape
from report_templates import (
    get_talking_point,
    get_severity,
    get_category,
    generate_executive_summary
)

# Set up Jinja2 environment
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(['html', 'xml'])
)

# Load the HTML template
template = env.get_template('report_template.html')

def generate_html_report(plugin_results, output_path='kast_report.html'):
    """
    Generates an HTML report from plugin results using Jinja2.
    
    Args:
        plugin_results (list): List of plugin result dictionaries.
        output_path (str): Path to save the generated HTML report.
    """
    all_issues = []
    detailed_results = {}

    for plugin in plugin_results:
        tool_name = plugin.get("tool", "Unknown Tool")
        detailed_results[tool_name] = {
            "summary": plugin.get("summary", ""),
            "details": plugin.get("details", ""),
            "report": plugin.get("report", "")
        }

        for issue in plugin.get("issues", []):
            issue_id = issue.get("id")
            all_issues.append({
                "id": issue_id,
                "description": issue.get("description", ""),
                "remediation": get_talking_point(issue_id),
                "severity": get_severity(issue_id),
                "category": get_category(issue_id)
            })

    # Generate executive summary
    executive_summary = generate_executive_summary(all_issues)

    # Render the HTML report
    html_content = template.render(
        executive_summary=executive_summary,
        issues=all_issues,
        detailed_results=detailed_results
    )

    # Save to file
    with open(output_path, 'w') as f:
        f.write(html_content)

    print(f"Report saved to {output_path}")
