import json
import os

from kast.core.severity import Severity

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
    Returns the canonical severity string for a given issue ID.

    Always returns one of "High", "Medium", "Low", "Informational", "Unknown"
    via the Severity enum's normalization. The historical "Info" spelling
    and the "Issue ID not found." sentinel are normalized to canonical
    values; downstream code (report builder, templates) sees one vocabulary.
    """
    issue = get_issue_metadata(issue_id)
    raw = issue.get("severity", "Unknown") if issue else "Unknown"
    return Severity.from_registry(raw).value

# Function to get the issue category
def get_category(issue_id):
    """
    Returns the category for a given issue ID.
    """
    issue = get_issue_metadata(issue_id)
    if issue:
        return issue.get("category", "Uncategorized")
        severity = issue.get("severity","Unknown")
        # Registry stores "Informational"; reports and templates use "Info".
        # Normalize here so badge counts, sort order, and templates all agree.
        if severity == "Informational":
            severity = "Info"
        return
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
    
    # Get display name from issue registry, fallback to issue_id if not found
    issue_metadata = get_issue_metadata(issue_id)
    display_name = issue_metadata.get("display_name", issue_id) if issue_metadata else issue_id

    return (
        f"- **{display_name}** ({severity}, {category})\n"
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
    # Keys match the canonical Severity enum values exactly.
    severities = {s.value: 0 for s in Severity}

    for issue in issues:
        issue_id = issue.get("id")
        category = get_category(issue_id)
        severity = get_severity(issue_id)  # Already canonical via Severity enum
        categories.add(category)
        if severity in severities:
            severities[severity] += 1
        else:
            severities[Severity.UNKNOWN.value] += 1

    # Build severity breakdown, excluding counts of 0, in severity order.
    severity_parts = []
    for sev in [s.value for s in Severity]:
        if severities[sev] > 0:
            severity_parts.append(f"{sev}={severities[sev]}")
    
    severity_breakdown = ", ".join(severity_parts) if severity_parts else "None"

    summary = (
        f"{len(issues)} potential issues were identified.\n"
        f"Categories involved: {', '.join(sorted(categories))}.\n"
        f"Severity breakdown: {severity_breakdown}."
    )
    return summary
