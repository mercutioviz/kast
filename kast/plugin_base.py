# kast/plugin_base.py
# Base class for all KAST plugins. Defines the interface and required methods.

import abc

class KastPlugin(abc.ABC):
    """
    Abstract base class for all KAST plugins.
    Each plugin must implement the run() method and provide metadata.
    """

    @abc.abstractmethod
    def run(self, target, options):
        """
        Run the plugin's scan against the target.
        Args:
            target (str): The target domain or IP.
            options (dict): Additional options for the scan.
        Returns:
            dict: Results conforming to the KAST result schema.
        """
        pass

    @property
    @abc.abstractmethod
    def name(self):
        """Return the unique name of the plugin."""
        pass

    @property
    @abc.abstractmethod
    def description(self):
        """Return a short description of the plugin."""
        pass

    @property
    def version(self):
        """Return the plugin version (optional)."""
        return "1.0"
