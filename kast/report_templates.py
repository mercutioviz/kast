import json
import os

# Path to the issue registry JSON file
ISSUE_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), 'data', 'issue_registry.json')

# Load issue metadata from the JSON file
try:
    with open(ISSUE_REGISTRY_PATH, 'r') as f:
        ISSUE_REGISTRY = json.load(f)
except FileNotFoundError:
    ISSUE_REGISTRY = {}
    print(f"Warning: Issue registry file not found at {ISSUE_REGISTRY_PATH}")
except json.JSONDecodeError:
    ISSUE_REGISTRY = {}
    print(f"Warning: Issue registry file is not valid JSON.")

# Function to get full metadata for a given issue ID
def get_issue_metadata(issue_id):
    """
    Returns the full metadata dictionary for a given issue ID.
    """
    return ISSUE_REGISTRY.get(issue_id)

# Function to get the remediation talking point
def get_talking_point(issue_id):
    """
    Returns the remediation string for a given issue ID.
    """
    issue = get_issue_metadata(issue_id)
    if issue:
        return issue.get("remediation", "No remediation available.")
    return "Issue ID not found."

# Function to get the severity level
def get_severity(issue_id):
    """
    Returns the severity level for a given issue ID.
    """
    issue = get_issue_metadata(issue_id)
    if issue:
        return issue.get("severity", "Unknown")
    return "Issue ID not found."

# Function to get the issue category
def get_category(issue_id):
    """
    Returns the category for a given issue ID.
    """
    issue = get_issue_metadata(issue_id)
    if issue:
        return issue.get("category", "Uncategorized")
    return "Issue ID not found."

# Function to format an issue for inclusion in a report
def format_issue_for_report(issue):
    """
    Takes an issue dictionary and returns a formatted string for the report.
    """
    issue_id = issue.get("id", "Unknown ID")
    description = issue.get("description", "No description provided.")
    remediation = get_talking_point(issue_id)
    severity = get_severity(issue_id)
    category = get_category(issue_id)

    return (
        f"- **{issue_id}** ({severity}, {category})\n"
        f"  - Description: {description}\n"
        f"  - Remediation: {remediation}\n"
    )

# Function to generate an executive summary from a list of issues
def generate_executive_summary(issues):
    """
    Takes a list of issue dictionaries and returns a high-level summary.
    """
    if not issues:
        return "No critical issues were found during the scan."

    categories = set()
    severities = {"Low": 0, "Medium": 0, "High": 0}

    for issue in issues:
        issue_id = issue.get("id")
        category = get_category(issue_id)
        severity = get_severity(issue_id)
        categories.add(category)
        if severity in severities:
            severities[severity] += 1

    summary = (
        f"{len(issues)} potential issues were identified.\n"
        f"Categories involved: {', '.join(categories)}.\n"
        f"Severity breakdown: High={severities['High']}, Medium={severities['Medium']}, Low={severities['Low']}."
    )
    return summary
