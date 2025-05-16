# kast/result_schema.py
# Defines the uniform result schema for all plugins.

from datetime import datetime

def base_result_schema(plugin_name, target):
    """
    Returns a base result dictionary for plugin results.
    """
    return {
        "plugin": plugin_name,
        "target": target,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": "success",  # or "error"
        "results": {},        # plugin-specific results go here
        "error": None         # error message if status == "error"
    }
