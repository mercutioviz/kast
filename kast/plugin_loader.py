# File: kast/plugin_loader.py
# Description: Loads all available plugins from the plugins directory.

import importlib
import pkgutil
import logging
from kast.plugin_base import KastPlugin

def load_plugins(selected_tools=None):
    import kast.plugins
    plugins = []
    for loader, module_name, is_pkg in pkgutil.iter_modules(kast.plugins.__path__):
        if selected_tools and module_name not in selected_tools:
            continue
        module = importlib.import_module(f"kast.plugins.{module_name}")
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and issubclass(obj, KastPlugin) and obj is not KastPlugin:
                plugins.append(obj())
    logging.info(f"Loaded plugins: {[p.name for p in plugins]}")
    return plugins
