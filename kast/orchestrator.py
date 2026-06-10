# orchestrator.py
"""
File: orchestrator.py
Description: Orchestrates the execution of KAST plugins, manages plugin
lifecycle, and aggregates results.

In v3 (Phase A4), the orchestrator receives already-instantiated plugin
instances from the caller (typically a PluginRegistry) rather than
plugin classes. The five duplicated try/except instantiation blocks
have been collapsed into the registry.
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime


class ScannerOrchestrator:
    def __init__(self, plugins, cli_args, output_dir, log, report_only=False):
        """
        :param plugins: List of plugin INSTANCES (already constructed via
            PluginRegistry). The orchestrator does not instantiate plugins.
        :param cli_args: Namespace from argparse.
        :param output_dir: Directory for plugin outputs.
        :param log: Logger instance.
        :param report_only: Whether to only generate reports from existing data.
        """
        self.plugins = plugins
        self.cli_args = cli_args
        self.output_dir = output_dir
        self.log = log
        self.report_only = report_only
        self.plugin_timings = []
        self.timings_lock = threading.Lock()

    def run(self):
        """Run all plugins according to CLI args and collect results."""
        results = []
        self.log.info("Starting scan for target: %s", self.cli_args.target)
        self.log.info(f"Scan mode: {self.cli_args.mode}")

        selected_plugins, filtered_out = self._filter_by_mode(
            self.plugins, self.cli_args.mode
        )

        self.log.info(
            f"Plugin filtering complete: {len(selected_plugins)} selected, "
            f"{len(filtered_out)} filtered out"
        )
        if filtered_out:
            self.log.info(
                "Filtered out plugins: "
                + ", ".join(f"{p.name} ({p.scan_type})" for p in filtered_out)
            )

        if self.cli_args.dry_run:
            self._print_dry_run(selected_plugins)
            return []

        if self.cli_args.parallel:
            max_workers = getattr(self.cli_args, "max_workers", 5)
            self.log.info(
                f"Running plugins in parallel mode with max {max_workers} workers."
            )
            results = self._run_plugins_with_dependencies(selected_plugins, max_workers)
        else:
            self.log.info("Running plugins sequentially.")
            for plugin in selected_plugins:
                results.append(self._run_plugin(plugin))

        self.log.info("Scan complete. %d plugins executed.", len(results))
        return results

    def _filter_by_mode(self, plugins, mode):
        """Split plugins into (selected, filtered_out) based on scan_type vs. mode."""
        selected = []
        filtered_out = []
        self.log.info(f"Filtering {len(plugins)} total plugins for mode: {mode}")
        for plugin in plugins:
            scan_type = getattr(plugin, "scan_type", "passive")
            if mode == "both" or scan_type == mode:
                selected.append(plugin)
                self.log.info(f"✓ Selected plugin: {plugin.name} (scan_type: {scan_type})")
            else:
                filtered_out.append(plugin)
                self.log.info(
                    f"✗ Filtered out plugin: {plugin.name} "
                    f"(scan_type: {scan_type}, required: {mode})"
                )
        return selected, filtered_out

    def _print_dry_run(self, selected_plugins):
        """Log what each selected plugin would do, without executing anything."""
        self.log.info("Dry run mode enabled. Showing what would be executed:")
        self.log.info("=" * 70)

        for plugin in selected_plugins:
            try:
                dry_run_info = plugin.get_dry_run_info(
                    self.cli_args.target, self.output_dir
                )

                self.log.info(f"\nPlugin: {plugin.display_name} ({plugin.name})")
                self.log.info(f"Type: {plugin.scan_type}")
                self.log.info(f"Priority: {plugin.priority}")
                self.log.info(
                    f"Description: {dry_run_info.get('description', plugin.description)}"
                )

                commands = dry_run_info.get("commands", [])
                if commands:
                    self.log.info("Commands that would be executed:")
                    for i, cmd in enumerate(commands, 1):
                        if len(commands) > 1:
                            self.log.info(f"  [{i}] {cmd}")
                        else:
                            self.log.info(f"  {cmd}")

                operations = dry_run_info.get("operations", "")
                if operations and not commands:
                    if isinstance(operations, list):
                        self.log.info("Operations that would be performed:")
                        for op in operations:
                            self.log.info(f"  {op}")
                    else:
                        self.log.info(f"Operations: {operations}")

                self.log.info("-" * 70)

            except Exception as e:
                self.log.error(
                    f"Error getting dry-run info for {plugin.name}: {e}"
                )
                self.log.info(
                    f"[DRY RUN] Would run plugin: {plugin.name} "
                    f"(scan_type: {plugin.scan_type})"
                )
                self.log.info("-" * 70)

        self.log.info("\nDry run complete. No actions were performed.")

    def _run_plugin(self, plugin):
        """Run a single plugin instance, capturing timing and disposition."""
        plugin_name = plugin.name

        timing_info = {
            "plugin_name": plugin_name,
            "start_timestamp": None,
            "end_timestamp": None,
            "duration_seconds": None,
            "status": "skipped",
        }

        start_time = None

        self.log.info(f"Checking availability for plugin: {plugin_name}")
        if not plugin.is_available():
            self.log.error(f"Plugin {plugin_name} is not available. Skipping.")
            timing_info["status"] = "unavailable"
            with self.timings_lock:
                self.plugin_timings.append(timing_info)
            return plugin.get_result_dict("fail", "Tool not available.")

        try:
            start_time = time.time()
            timing_info["start_timestamp"] = datetime.now().isoformat()

            self.log.info(f"Running plugin: {plugin_name}")
            raw_result = plugin.run(
                self.cli_args.target, self.output_dir, self.report_only
            )
            self.log.info(
                f"Plugin {plugin_name} finished with disposition: "
                f"{raw_result.get('disposition')}"
            )
            processed_path = plugin.post_process(raw_result, self.output_dir)
            self.log.info(
                f"Plugin {plugin_name} post-processed output: {processed_path}"
            )

            end_time = time.time()
            timing_info["end_timestamp"] = datetime.now().isoformat()
            timing_info["duration_seconds"] = round(end_time - start_time, 2)
            timing_info["status"] = raw_result.get("disposition", "unknown")

            with self.timings_lock:
                self.plugin_timings.append(timing_info)
            return raw_result

        except Exception as e:
            end_time = time.time()
            timing_info["end_timestamp"] = datetime.now().isoformat()
            if start_time is not None:
                timing_info["duration_seconds"] = round(end_time - start_time, 2)
            timing_info["status"] = "failed"
            timing_info["error"] = str(e)

            with self.timings_lock:
                self.plugin_timings.append(timing_info)
            self.log.exception(f"Plugin {plugin_name} failed with exception: {e}")
            return plugin.get_result_dict("fail", str(e))

    def _run_plugins_with_dependencies(self, selected_plugins, max_workers):
        """
        Run plugins in parallel while respecting their declared dependencies.

        :param selected_plugins: List of plugin instances to run (already filtered).
        :param max_workers: Maximum number of parallel workers.
        :return: List of plugin results.
        """
        results = []
        completed_plugins = {}  # plugin_name -> result
        pending_plugins = {p.name: p for p in selected_plugins}  # name -> instance
        futures = {}            # future -> plugin_instance
        plugin_dependency_states = {}  # name -> last logged "waiting" reason

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            while pending_plugins or futures:
                newly_submitted = False

                # Submit any plugins whose dependencies are now satisfied.
                for name in list(pending_plugins.keys()):
                    plugin = pending_plugins[name]
                    deps_satisfied, reason = plugin.check_dependencies(completed_plugins)

                    if deps_satisfied:
                        self.log.info(f"Submitting plugin {plugin.name} to executor")
                        future = executor.submit(self._run_plugin, plugin)
                        futures[future] = plugin
                        del pending_plugins[name]
                        newly_submitted = True
                    else:
                        last_reason = plugin_dependency_states.get(plugin.name)
                        if last_reason != reason:
                            self.log.debug(
                                f"Plugin {plugin.name} waiting on dependencies: {reason}"
                            )
                            plugin_dependency_states[plugin.name] = reason

                # Detect deadlock: nothing submittable, nothing running, but plugins remain.
                if not newly_submitted and pending_plugins and not futures:
                    self.log.error(
                        "Dependency deadlock detected! Some plugins cannot run:"
                    )
                    for plugin in list(pending_plugins.values()):
                        _, reason = plugin.check_dependencies(completed_plugins)
                        self.log.error(f"  - {plugin.name}: {reason}")
                        error_result = plugin.get_result_dict(
                            "fail", f"Dependency deadlock: {reason}"
                        )
                        results.append(error_result)
                        completed_plugins[plugin.name] = error_result
                    break

                # Block on the first future to complete, then process it.
                # Note: v2 had `done, _ = as_completed(futures), None` here, which
                # discarded the iterator and turned the loop into a busy-wait
                # (audit § 6.1). next(as_completed(...)) is the correct blocking call.
                if futures:
                    done_future = next(as_completed(futures))
                    plugin = futures[done_future]
                    plugin_name = plugin.name
                    try:
                        result = done_future.result()
                        results.append(result)
                        completed_plugins[plugin_name] = result
                        self.log.info(
                            f"Plugin {plugin_name} completed with disposition: "
                            f"{result.get('disposition')}"
                        )
                    except Exception as e:
                        self.log.error(f"Plugin {plugin_name} raised an exception: {e}")
                        error_result = plugin.get_result_dict(
                            "fail", f"Future exception: {str(e)}"
                        )
                        results.append(error_result)
                        completed_plugins[plugin_name] = error_result
                    del futures[done_future]


        return results

    def get_plugin_timings(self):
        """Return the list of plugin timing information collected during run()."""
        return self.plugin_timings
