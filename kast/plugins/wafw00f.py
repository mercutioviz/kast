# File: kast/plugins/wafw00f.py
# Description: Plugin for running wafw00f to detect WAFs.

import shutil
import subprocess
import logging
from kast.plugin_base import KastPlugin, PluginResult

class Wafw00fPlugin(KastPlugin):
    name = "wafw00f"
    description = "Detects if a WAF is present using wafw00f"

    def run(self, target):
        wafw00f_path = shutil.which("wafw00f")
        if not wafw00f_path:
            logging.warning("wafw00f binary not found in PATH. Skipping wafw00f scan.")
            return PluginResult(
                tool_name=self.name,
                target=target,
                success=False,
                results={},
                error="wafw00f binary not found"
            )
        try:
            proc = subprocess.run(
                [wafw00f_path, "-a", target],
                capture_output=True,
                text=True,
                timeout=60
            )
            if proc.returncode == 0:
                return PluginResult(
                    tool_name=self.name,
                    target=target,
                    success=True,
                    results={"output": proc.stdout}
                )
            else:
                return PluginResult(
                    tool_name=self.name,
                    target=target,
                    success=False,
                    results={"output": proc.stdout, "stderr": proc.stderr},
                    error=f"wafw00f exited with code {proc.returncode}"
                )
        except Exception as e:
            logging.error(f"Exception running wafw00f: {e}")
            return PluginResult(
                tool_name=self.name,
                target=target,
                success=False,
                results={},
                error=str(e)
            )
