"""Plugin discovery and instantiation registry for kast.

Single source of truth for the plugin lifecycle. Discovers plugin classes
once, caches instances, and exposes a clean API to consumers (orchestrator,
main entry point, dry-run / show-deps utilities, kast --config-schema, kast
--list-plugins).

Replaces the v2 pattern repeated in five sites (audit § 3.1):

    plugins = discover_plugins(log)
    for plugin_cls in plugins:
        class MinimalArgs:
            verbose = False
        try:
            try:
                instance = plugin_cls(MinimalArgs(), config_manager)
            except TypeError:
                instance = plugin_cls(MinimalArgs())
        except Exception as e:
            log.error(...)

Phase A4 migrates the existing call sites to PluginRegistry; Phase A5
removes the TypeError fallback once schemas move to class attributes
and identity is settable without going through ``__init__``.
"""

from __future__ import annotations

import logging
from typing import Optional

from kast.plugins.base import KastPlugin
from kast.utils import discover_plugins as _discover_plugin_classes


def make_minimal_args() -> object:
    """Return a stand-in for argparse.Namespace.

    Used when a registry needs to instantiate plugins for metadata or schema
    enumeration before real CLI args are parsed (e.g., ``kast --list-plugins``,
    ``kast --config-schema``). Carries the attributes plugins access during
    ``__init__`` and ``debug()``.
    """

    class _Args:
        verbose = False
        mode = "both"

    return _Args()


class PluginRegistry:
    """Discovers, caches, and dispenses kast plugins.

    Construct one PluginRegistry per kast invocation. The registry lazily
    discovers plugin classes on first access and caches instances thereafter,
    so consumers can ask for the same plugin multiple times without paying
    repeated ``__init__`` cost.

    Typical usage:

        registry = PluginRegistry(logger, cli_args=args, config_manager=cm)
        for plugin in registry.filter_by_mode(args.mode):
            plugin.run(target, output_dir, report_only)

    For metadata-only use cases (list-plugins, config-schema export) where
    real CLI args may not yet exist, omit cli_args and config_manager:

        registry = PluginRegistry(logger)
        for cls in registry.discover():
            print(cls.__name__)
    """

    def __init__(
        self,
        logger: logging.Logger,
        cli_args: object = None,
        config_manager: Optional[object] = None,
    ) -> None:
        self.logger = logger
        self.cli_args = cli_args if cli_args is not None else make_minimal_args()
        self.config_manager = config_manager
        self._classes: Optional[list[type[KastPlugin]]] = None
        self._instances: dict[str, KastPlugin] = {}
        self._loaded = False

    def discover(self) -> list[type[KastPlugin]]:
        """Return all plugin classes sorted by priority.

        Cached after first call. Does not instantiate plugins.
        """
        if self._classes is None:
            self._classes = list(_discover_plugin_classes(self.logger))
        return self._classes

    def all_instances(self) -> list[KastPlugin]:
        """Return one instance per discovered plugin, sorted by priority.

        Plugins that fail to instantiate are logged and skipped.
        """
        self._ensure_loaded()
        # Re-sort by priority each call in case discovery order ever drifts.
        return sorted(self._instances.values(), key=lambda p: p.priority)

    def get(self, name: str) -> KastPlugin:
        """Return the cached instance of the named plugin.

        Raises KeyError if no plugin with that name exists or if the plugin
        failed to instantiate.
        """
        self._ensure_loaded()
        if name not in self._instances:
            raise KeyError(f"No plugin named {name!r}")
        return self._instances[name]

    def filter_by_mode(self, mode: str) -> list[KastPlugin]:
        """Return instances whose ``scan_type`` matches the mode.

        ``mode`` is one of ``"active"``, ``"passive"``, or ``"both"``.
        ``"both"`` returns every instance.
        """
        return [
            inst
            for inst in self.all_instances()
            if mode == "both" or getattr(inst, "scan_type", "passive") == mode
        ]

    # -- internals ----------------------------------------------------------

    def _ensure_loaded(self) -> None:
        """Instantiate every discovered plugin, caching by name.

        Idempotent. Plugins that fail to instantiate are logged and excluded
        from the cache (matching v2 behavior of "skip the broken plugin and
        keep going" — never crash the orchestrator).
        """
        if self._loaded:
            return
        for cls in self.discover():
            inst = self._instantiate(cls)
            if inst is not None:
                self._instances[inst.name] = inst
        self._loaded = True

    def _instantiate(self, cls: type[KastPlugin]) -> Optional[KastPlugin]:
        """Construct a plugin instance with the registry's cli_args/config_manager.

        Phase A5 unified all plugins on ``__init__(self, cli_args, config_manager=None)``,
        so the legacy TypeError fallback is no longer needed.
        """
        try:
            return cls(self.cli_args, self.config_manager)
        except Exception as e:
            self.logger.error(
                f"Error instantiating plugin {cls.__name__}: {e}"
            )
            return None
