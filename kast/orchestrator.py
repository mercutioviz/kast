# orchestrator.py
"""
File: orchestrator.py
Description: Orchestrates the execution of KAST plugins, manages plugin lifecycle, and aggregates results.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed

class ScannerOrchestrator:
    def __init__(self, plugins, cli_args, output_dir, log):
        """
        :param plugins: List of plugin classes (not instances)
        :param cli_args: Namespace from argparse
        :param output_dir: Directory for plugin outputs
        :param log: Logger instance
        """
        self.plugins = plugins
        self.cli_args = cli_args
        self.output_dir = output_dir
        self.log = log

    def run(self):
        """
        Run all plugins according to CLI args and collect results.
        """
        results = []
        self.log.info("Starting scan for target: %s", self.cli_args.target)
        if self.cli_args.dry_run:
            self.log.info("Dry run mode enabled. No plugins will be executed.")
            for plugin_cls in self.plugins:
                plugin = plugin_cls(self.cli_args)
                self.log.info(f"[DRY RUN] Would run plugin: {plugin.name}")
            return []

        # Filter plugins by scan type (active/passive)
        selected_plugins = [
            p for p in self.plugins
            if getattr(p(self.cli_args), "scan_type", "passive") == self.cli_args.mode
        ]

        if self.cli_args.parallel:
            self.log.info("Running plugins in parallel mode.")
            with ThreadPoolExecutor() as executor:
                future_to_plugin = {
                    executor.submit(self._run_plugin, plugin_cls): plugin_cls
                    for plugin_cls in selected_plugins
                }
                for future in as_completed(future_to_plugin):
                    result = future.result()
                    results.append(result)
        else:
            self.log.info("Running plugins sequentially.")
            for plugin_cls in selected_plugins:
                result = self._run_plugin(plugin_cls)
                results.append(result)

        self.log.info("Scan complete. %d plugins executed.", len(results))
        return results

    def _run_plugin(self, plugin_cls):
        plugin = plugin_cls(self.cli_args)
        self.log.info(f"Checking availability for plugin: {plugin.name}")
        if not plugin.is_available():
            self.log.error(f"Plugin {plugin.name} is not available. Skipping.")
            return plugin.get_result_dict("fail", "Tool not available.")
        try:
            self.log.info(f"Running plugin: {plugin.name}")
            result = plugin.run(self.cli_args.target, self.output_dir)
            self.log.info(f"Plugin {plugin.name} finished with disposition: {result.get('disposition')}")
            return result
        except Exception as e:
            self.log.exception(f"Plugin {plugin.name} failed with exception: {e}")
            return plugin.get_result_dict("fail", str(e))