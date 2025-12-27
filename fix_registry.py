import json

# Read the existing registry
with open('kast/data/issue_registry.json', 'r') as f:
    existing_registry = json.load(f)

print(f"Loaded {len(existing_registry)} existing entries from registry")

# Define new or updated entries
updates = {
    "TLSv1.0": {
        "display_name": "TLSv1.0",
        "description": "TLSv1.0 is a deprecated encryption protocol that lacks modern security features.",
        "remediation": "Upgrade to TLSv1.2 or TLSv1.3. A WAF can enforce secure protocols by terminating TLS connections and redirecting traffic through secure channels.",
        "severity": "High",
        "category": "Encryption",
        "waf_addressable": True,
        "remediation_approach": "waf",
        "code_fix_timeframe": "1-2 weeks",
        "waf_deployment_timeframe": "1-2 days"
    }
}

# Update the registry with new entries (merging with existing)
for key, value in updates.items():
    if key in existing_registry:
        print(f"Updating existing entry: {key}")
    else:
        print(f"Adding new entry: {key}")
    existing_registry[key] = value

# Write the updated registry back
with open('kast/data/issue_registry.json', 'w') as f:
    json.dump(existing_registry, f, indent=2)

print(f"Registry updated successfully with {len(existing_registry)} total entries")
