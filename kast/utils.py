# utils.py
import sys
import os
import importlib.util
from pathlib import Path
import inspect
from abc import ABC

# Ensure parent directory of 'kast' is in sys.path
kast_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(kast_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def discover_plugins(log):
    plugins = []
    plugins_dir = Path(kast_dir) / "plugins"
    for file in plugins_dir.glob("*_plugin.py"):
        log.debug(f"Found plugin file: {file}")
        module_name = f"kast.plugins.{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr in dir(module):
            obj = getattr(module, attr)
            if isinstance(obj, type) and hasattr(obj, "run") and hasattr(obj, "is_available") and not inspect.isabstract(obj):
                plugins.append(obj)
    
    # Sort plugins by priority
    plugins.sort(key=lambda x: x.priority)    
    return plugins
