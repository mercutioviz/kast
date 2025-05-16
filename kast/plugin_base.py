# File: kast/plugin_base.py
# Description: Defines the base class for all KAST plugins and the uniform result schema.

import json
from abc import ABC, abstractmethod

class PluginResult:
    def __init__(self, tool_name, target, success, results, error=None, extra=None):
        self.tool_name = tool_name
        self.target = target
        self.success = success
        self.results = results  # Tool-specific results (dict)
        self.error = error
        self.extra = extra or {}

    def to_dict(self):
        return {
            "tool_name": self.tool_name,
            "target": self.target,
            "success": self.success,
            "results": self.results,
            "error": self.error,
            "extra": self.extra,
        }

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)

class KastPlugin(ABC):
    name = "base"
    description = "Base plugin class"

    @abstractmethod
    def run(self, target):
        """Run the plugin against the target. Returns a PluginResult."""
        pass
