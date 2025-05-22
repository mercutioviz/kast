# base.py
"""
File: base.py
Description: Base class for all KAST plugins. Provides required interface and properties.
"""

from abc import ABC, abstractmethod
from datetime import datetime
import shutil

class KastPlugin(ABC):
    """
    Abstract base class for all KAST plugins.
    """

    def __init__(self, cli_args):
        """
        Initialize the plugin with CLI arguments.
        :param cli_args: Namespace object from argparse containing CLI arguments.
        """
        self.cli_args = cli_args
        self.name = "BasePlugin"
        self.description = "Abstract base class for KAST plugins."
        self.scan_type = "passive"  # or "active"
        self.output_type = "stdout"  # or "file"

    @abstractmethod
    def run(self, target, output_dir):
        """
        Run the plugin scan.
        :param target: The target domain or IP to scan.
        :param output_dir: Directory to write output files, if applicable.
        :return: results dictionary
        """
        return self.get_result_dict("fail", "Not implemented.")

    def debug(self, message):
        """
        Print debug messages if verbose mode is enabled.
        """
        if getattr(self.cli_args, "verbose", False):
            print(f"[DEBUG] {self.name}: {message}")

    def get_metadata(self):
        """
        Return plugin metadata as a dictionary.
        """
        return {
            "name": self.name,
            "description": self.description,
            "scan_type": self.scan_type,
            "output_type": self.output_type,
        }

    def get_result_dict(self, disposition, results):
        """
        Standardized result dictionary for all plugins.
        :param disposition: 'success' or 'fail'
        :param results: plugin output (string, dict, etc.)
        :return: dict
        """
        return {
            "name": self.name,
            "timestamp": datetime.utcnow().isoformat(),
            "disposition": disposition,
            "results": results,
        }

    @abstractmethod
    def is_available(self):
        """
        Check if the required tool for this plugin is available.
        :return: True if available, False otherwise.
        """
        pass