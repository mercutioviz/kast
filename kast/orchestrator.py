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
    def __init__(self, plugins, cli_args, output_dir, log, report_only=False, config_manager=None):
        """
        :param plugins: List of plugin classes (not instances)
        :param cli_args: Namespace from argparse
        :param output_dir: Directory for plugin outputs
        :param log: Logger instance
        :param report_only: Whether to only generate reports from existing data
        :param config_manager: ConfigManager instance for plugin configuration
        """
        self.plugins = plugins
        self.cli_args = cli_args
        self.output_dir = output_dir
        self.log = log
        self.report_only = report_only
        self.config_manager = config_manager
        self.plugin_timings = []
        self.timings_lock = threading.Lock()  # Thread-safe access to plugin_timings

    def run(self):
        """
        Run all plugins according to CLI args and collect results.
        """
        results = []
        self.log.info("Starting scan for target: %s", self.cli_args.target)
        self.log.info(f"Scan mode: {self.cli_args.mode}")
        
        if self.cli_args.dry_run:
            self.log.info("Dry run mode enabled. Showing what would be executed:")
            self.log.info("=" * 70)
            
            # Apply same filtering logic as normal execution
            for plugin_cls in self.plugins:
                try:
                    plugin_instance = plugin_cls(self.cli_args, self.config_manager)
                    plugin_scan_type = getattr(plugin_instance, "scan_type", "passive")
                    
                    # Check if plugin should run based on mode
                    should_run = (
                        self.cli_args.mode == "both" or 
                        plugin_scan_type == self.cli_args.mode
                    )
                    
                    if should_run:
                        # Get dry-run information from the plugin
                        try:
                            dry_run_info = plugin_instance.get_dry_run_info(
                                self.cli_args.target,
                                self.output_dir
                            )
                            
                            self.log.info(f"\nPlugin: {plugin_instance.display_name} ({plugin_instance.name})")
                            self.log.info(f"Type: {plugin_scan_type}")
                            self.log.info(f"Priority: {plugin_instance.priority}")
                            self.log.info(f"Description: {dry_run_info.get('description', plugin_instance.description)}")
                            
                            # Show commands if available (for external tool plugins)
                            commands = dry_run_info.get('commands', [])
                            if commands:
                                self.log.info("Commands that would be executed:")
                                for i, cmd in enumerate(commands, 1):
                                    if len(commands) > 1:
                                        self.log.info(f"  [{i}] {cmd}")
                                    else:
                                        self.log.info(f"  {cmd}")
                            
                            # Show operations for internal logic plugins
                            operations = dry_run_info.get('operations', '')
                            if operations and not commands:
                                if isinstance(operations, list):
                                    self.log.info("Operations that would be performed:")
                                    for op in operations:
                                        self.log.info(f"  {op}")
                                else:
                                    self.log.info(f"Operations: {operations}")
                            
                            self.log.info("-" * 70)
                            
                        except Exception as e:
                            self.log.error(f"Error getting dry-run info for {plugin_instance.name}: {e}")
                            self.log.info(f"[DRY RUN] Would run plugin: {plugin_instance.name} (scan_type: {plugin_scan_type})")
                            self.log.info("-" * 70)
                    else:
                        self.log.debug(f"[SKIPPED] {plugin_instance.name} (scan_type: {plugin_scan_type}, mode filter: {self.cli_args.mode})")
                        
                except Exception as e:
                    self.log.error(f"Error checking plugin {plugin_cls.__name__}: {e}")
            
            self.log.info("\nDry run complete. No actions were performed.")
            return []

        # Filter plugins by scan type (active/passive/both)
        # Cache plugin metadata to avoid creating unnecessary temporary instances
        selected_plugins = []
        filtered_out_plugins = []
        
        self.log.info(f"Filtering {len(self.plugins)} total plugins for mode: {self.cli_args.mode}")
        
        for plugin_cls in self.plugins:
            try:
                # Create instance once to check scan_type
                plugin_instance = plugin_cls(self.cli_args, self.config_manager)
                plugin_scan_type = getattr(plugin_instance, "scan_type", "passive")
                
                # Check if plugin should run based on mode
                should_run = (
                    self.cli_args.mode == "both" or 
                    plugin_scan_type == self.cli_args.mode
                )
                
                if should_run:
                    selected_plugins.append(plugin_cls)
                    self.log.info(f"✓ Selected plugin: {plugin_instance.name} (scan_type: {plugin_scan_type})")
                else:
                    filtered_out_plugins.append((plugin_instance.name, plugin_scan_type))
                    self.log.info(f"✗ Filtered out plugin: {plugin_instance.name} (scan_type: {plugin_scan_type}, required: {self.cli_args.mode})")
            except Exception as e:
                self.log.error(f"Error instantiating plugin {plugin_cls.__name__} for filtering: {e}")
        
        # Log summary of filtering
        self.log.info(f"Plugin filtering complete: {len(selected_plugins)} selected, {len(filtered_out_plugins)} filtered out")
        if filtered_out_plugins:
            self.log.info(f"Filtered out plugins: {', '.join([f'{name} ({scan_type})' for name, scan_type in filtered_out_plugins])}")

        if self.cli_args.parallel:
            # Get max_workers from CLI args, default to 5 for conservative security scanning
            max_workers = getattr(self.cli_args, 'max_workers', 5)
            self.log.info(f"Running plugins in parallel mode with max {max_workers} workers.")
            
            # Run plugins with dependency resolution
            results = self._run_plugins_with_dependencies(selected_plugins, max_workers)
        else:
            self.log.info("Running plugins sequentially.")
            for plugin_cls in selected_plugins:
                result = self._run_plugin(plugin_cls)
                results.append(result)

        self.log.info("Scan complete. %d plugins executed.", len(results))
        return results

    def _run_plugin(self, plugin_cls):
        plugin = plugin_cls(self.cli_args, self.config_manager)
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
    
    def _run_plugins_with_dependencies(self, selected_plugins, max_workers):
        """
        Run plugins in parallel while respecting dependencies.
        
        :param selected_plugins: List of plugin classes to run
        :param max_workers: Maximum number of parallel workers
        :return: List of plugin results
        """
        results = []
        completed_plugins = {}  # plugin_name -> result
        pending_plugins = {}    # plugin_cls -> plugin_instance
        futures = {}            # future -> (plugin_cls, plugin_instance)
        plugin_dependency_states = {}  # Track last logged reason per plugin to avoid spam
        
        # Create instances and map by name for dependency checking
        for plugin_cls in selected_plugins:
            try:
                plugin_instance = plugin_cls(self.cli_args, self.config_manager)
                pending_plugins[plugin_cls] = plugin_instance
            except Exception as e:
                self.log.error(f"Error instantiating plugin {plugin_cls.__name__}: {e}")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Keep submitting plugins as dependencies are satisfied
            while pending_plugins or futures:
                # Submit plugins whose dependencies are satisfied
                newly_submitted = False
                for plugin_cls in list(pending_plugins.keys()):
                    plugin = pending_plugins[plugin_cls]
                    
                    # Check if dependencies are satisfied
                    deps_satisfied, reason = plugin.check_dependencies(completed_plugins)
                    
                    if deps_satisfied:
                        self.log.info(f"Submitting plugin {plugin.name} to executor")
                        future = executor.submit(self._run_plugin, plugin_cls)
                        futures[future] = (plugin_cls, plugin)
                        del pending_plugins[plugin_cls]
                        newly_submitted = True
                    else:
                        # Only log if the dependency reason has changed
                        current_reason = reason
                        last_reason = plugin_dependency_states.get(plugin.name)
                        
                        if last_reason != current_reason:
                            self.log.debug(f"Plugin {plugin.name} waiting on dependencies: {reason}")
                            plugin_dependency_states[plugin.name] = current_reason
                
                # If no plugins were submitted and we still have pending plugins,
                # check if we're in a deadlock situation
                if not newly_submitted and pending_plugins and not futures:
                    self.log.error("Dependency deadlock detected! Some plugins cannot run:")
                    for plugin_cls, plugin in pending_plugins.items():
                        _, reason = plugin.check_dependencies(completed_plugins)
                        self.log.error(f"  - {plugin.name}: {reason}")
                        # Create error result for deadlocked plugins
                        error_result = plugin.get_result_dict("fail", f"Dependency deadlock: {reason}")
                        results.append(error_result)
                        completed_plugins[plugin.name] = error_result
                    break
                
                # Wait for at least one plugin to complete
                if futures:
                    done, _ = as_completed(futures), None
                    for future in list(futures.keys()):
                        if future.done():
                            plugin_cls, plugin = futures[future]
                            plugin_name = plugin.name
                            
                            try:
                                result = future.result()
                                results.append(result)
                                completed_plugins[plugin_name] = result
                                self.log.info(f"Plugin {plugin_name} completed with disposition: {result.get('disposition')}")
                            except Exception as e:
                                self.log.error(f"Plugin {plugin_name} raised an exception: {e}")
                                error_result = plugin.get_result_dict("fail", f"Future exception: {str(e)}")
                                results.append(error_result)
                                completed_plugins[plugin_name] = error_result
                            
                            del futures[future]
                            break  # Break to check for newly submittable plugins
        
        return results
    
    def get_plugin_timings(self):
        """
        Return the list of plugin timing information.
        
        :return: List of dictionaries containing plugin timing data
        """
        return self.plugin_timings
