# kast/plugin_loader.py
# Dynamically loads plugins from the plugins directory.

import importlib
import pkgutil
from .plugin_base import KastPlugin

def load_plugins():
    """
    Discover and load all plugins in the plugins directory.
    Returns:
        dict: Mapping of plugin name to plugin class.
    """
    import kast.plugins
    plugins = {}
    for loader, module_name, is_pkg in pkgutil.iter_modules(kast.plugins.__path__):
        module = importlib.import_module(f'kast.plugins.{module_name}')
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and issubclass(obj, KastPlugin) and obj is not KastPlugin:
                plugins[obj().name] = obj
    return plugins
