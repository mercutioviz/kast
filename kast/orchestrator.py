# orchestrator.py
"""
File: orchestrator.py
Description: Orchestrates the execution of KAST plugins, manages plugin lifecycle, and aggregates results.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from datetime import datetime
import threading

class ScannerOrchestrator:
    def __init__(self, plugins, cli_args, output_dir, log, report_only=False):
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
        self.report_only = report_only
        self.plugin_timings = []
        self.timings_lock = threading.Lock()  # Thread-safe access to plugin_timings

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
        # Cache plugin metadata to avoid creating unnecessary temporary instances
        selected_plugins = []
        for plugin_cls in self.plugins:
            try:
                # Create instance once to check scan_type
                plugin_instance = plugin_cls(self.cli_args)
                if getattr(plugin_instance, "scan_type", "passive") == self.cli_args.mode:
                    selected_plugins.append(plugin_cls)
            except Exception as e:
                self.log.error(f"Error instantiating plugin {plugin_cls.__name__} for filtering: {e}")

        if self.cli_args.parallel:
            # Get max_workers from CLI args, default to 5 for conservative security scanning
            max_workers = getattr(self.cli_args, 'max_workers', 5)
            self.log.info(f"Running plugins in parallel mode with max {max_workers} workers.")
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_plugin = {
                    executor.submit(self._run_plugin, plugin_cls): plugin_cls
                    for plugin_cls in selected_plugins
                }
                for future in as_completed(future_to_plugin):
                    plugin_cls = future_to_plugin[future]
                    plugin_name = getattr(plugin_cls, '__name__', 'Unknown')
                    try:
                        result = future.result()
                        results.append(result)
                    except Exception as e:
                        self.log.error(f"Future for plugin {plugin_name} raised an exception: {e}")
                        # Create a minimal plugin instance to get result_dict format
                        try:
                            plugin_instance = plugin_cls(self.cli_args)
                            error_result = plugin_instance.get_result_dict("fail", f"Future exception: {str(e)}")
                            results.append(error_result)
                        except Exception as inner_e:
                            self.log.error(f"Could not create error result for {plugin_name}: {inner_e}")
        else:
            self.log.info("Running plugins sequentially.")
            for plugin_cls in selected_plugins:
                result = self._run_plugin(plugin_cls)
                results.append(result)

        self.log.info("Scan complete. %d plugins executed.", len(results))
        return results

    def _run_plugin(self, plugin_cls):
        plugin = plugin_cls(self.cli_args)
        plugin_name = plugin.name
        
        # Initialize timing info
        timing_info = {
            "plugin_name": plugin_name,
            "start_timestamp": None,
            "end_timestamp": None,
            "duration_seconds": None,
            "status": "skipped"
        }
        
        # Initialize start_time to None to avoid undefined variable in exception handler
        start_time = None
        
        self.log.info(f"Checking availability for plugin: {plugin_name}")
        if not plugin.is_available():
            self.log.error(f"Plugin {plugin_name} is not available. Skipping.")
            timing_info["status"] = "unavailable"
            # Thread-safe append
            with self.timings_lock:
                self.plugin_timings.append(timing_info)
            return plugin.get_result_dict("fail", "Tool not available.")
        
        try:
            # Capture start time
            start_time = time.time()
            timing_info["start_timestamp"] = datetime.now().isoformat()
            
            self.log.info(f"Running plugin: {plugin_name}")
            raw_result = plugin.run(self.cli_args.target, self.output_dir, self.report_only)
            self.log.info(f"Plugin {plugin_name} finished with disposition: {raw_result.get('disposition')}")
            processed_path = plugin.post_process(raw_result, self.output_dir)
            self.log.info(f"Plugin {plugin_name} post-processed output: {processed_path}")
            
            # Capture end time
            end_time = time.time()
            timing_info["end_timestamp"] = datetime.now().isoformat()
            timing_info["duration_seconds"] = round(end_time - start_time, 2)
            timing_info["status"] = raw_result.get('disposition', 'unknown')
            
            # Thread-safe append
            with self.timings_lock:
                self.plugin_timings.append(timing_info)
            return raw_result
        except Exception as e:
            # Capture end time even on failure
            end_time = time.time()
            timing_info["end_timestamp"] = datetime.now().isoformat()
            # Only calculate duration if start_time was set
            if start_time is not None:
                timing_info["duration_seconds"] = round(end_time - start_time, 2)
            timing_info["status"] = "failed"
            timing_info["error"] = str(e)
            
            # Thread-safe append
            with self.timings_lock:
                self.plugin_timings.append(timing_info)
            self.log.exception(f"Plugin {plugin_name} failed with exception: {e}")
            return plugin.get_result_dict("fail", str(e))
    
    def get_plugin_timings(self):
        """
        Return the list of plugin timing information.
        
        :return: List of dictionaries containing plugin timing data
        """
        return self.plugin_timings
