"""Tests for PluginRegistry (kast.registry).

The registry is the single source of truth for plugin discovery and
instantiation. These tests pin down the surface area so Phase A4 can
migrate the five duplicated call sites against a known contract.
"""

import logging

import pytest

from kast.registry import PluginRegistry, make_minimal_args


@pytest.fixture
def logger():
    return logging.getLogger("test.registry")


@pytest.fixture
def registry(logger):
    return PluginRegistry(logger)


# -- discover() --------------------------------------------------------------


def test_discover_returns_known_plugins(registry):
    """Discovery finds all the well-known plugins by class name."""
    classes = registry.discover()
    class_names = {c.__name__ for c in classes}
    assert "WhatWebPlugin" in class_names
    assert "Wafw00fPlugin" in class_names
    assert "TestsslPlugin" in class_names
    assert "ZapPlugin" in class_names
    assert "ObservatoryPlugin" in class_names


def test_discover_skips_template(registry):
    """TemplatePlugin is loaded into the module but never returned by discover()."""
    classes = registry.discover()
    class_names = {c.__name__ for c in classes}
    assert "TemplatePlugin" not in class_names


def test_discover_returns_sorted_by_priority(registry):
    """Discovery order is by ascending priority."""
    classes = registry.discover()
    priorities = [c.priority for c in classes]
    assert priorities == sorted(priorities), (
        f"plugin classes not sorted by priority: {priorities}"
    )


def test_discover_is_cached(registry):
    """Calling discover() twice yields the identical list (no re-walk)."""
    first = registry.discover()
    second = registry.discover()
    assert first is second


# -- all_instances() ---------------------------------------------------------


def test_all_instances_returns_one_per_plugin(registry):
    """Every discovered plugin gets exactly one cached instance."""
    instances = registry.all_instances()
    names = [i.name for i in instances]
    # No duplicates
    assert len(names) == len(set(names)), f"duplicate plugin names: {names}"
    # And the count matches the number of discovered classes
    assert len(instances) == len(registry.discover())


def test_all_instances_sorted_by_priority(registry):
    """Instances are returned in priority order."""
    instances = registry.all_instances()
    priorities = [i.priority for i in instances]
    assert priorities == sorted(priorities)


def test_all_instances_are_cached(registry):
    """Repeated calls return the same instance objects."""
    first_call = {i.name: id(i) for i in registry.all_instances()}
    second_call = {i.name: id(i) for i in registry.all_instances()}
    assert first_call == second_call


# -- get() -------------------------------------------------------------------


def test_get_by_name_returns_correct_instance(registry):
    plugin = registry.get("whatweb")
    assert plugin.name == "whatweb"
    assert plugin.scan_type == "passive"


def test_get_caches_instance_identity(registry):
    """get() returns the same instance object across calls."""
    first = registry.get("whatweb")
    second = registry.get("whatweb")
    assert first is second


def test_get_unknown_raises_keyerror(registry):
    with pytest.raises(KeyError, match="nonexistent_plugin"):
        registry.get("nonexistent_plugin")


# -- filter_by_mode() --------------------------------------------------------


def test_filter_by_mode_passive_excludes_active(registry):
    passive = registry.filter_by_mode("passive")
    assert len(passive) > 0
    for plugin in passive:
        assert plugin.scan_type == "passive"


def test_filter_by_mode_active_returns_zap(registry):
    """ZAP is the only active plugin in v2.14.5."""
    active = registry.filter_by_mode("active")
    names = {p.name for p in active}
    assert "zap" in names
    for plugin in active:
        assert plugin.scan_type == "active"


def test_filter_by_mode_both_returns_everything(registry):
    both = registry.filter_by_mode("both")
    every = registry.all_instances()
    assert len(both) == len(every)


# -- make_minimal_args() -----------------------------------------------------


def test_minimal_args_has_required_attributes():
    """The minimal args stand-in carries what plugins access during __init__."""
    args = make_minimal_args()
    assert args.verbose is False
    assert args.mode == "both"


# -- instantiation safety ---------------------------------------------------


class _ExplodesOnInit:
    """Test fixture: raises on construction, simulating a broken plugin."""

    name = "explodes"
    priority = 999

    def __init__(self, cli_args, config_manager=None):
        raise RuntimeError("simulated init failure")


def test_instantiate_failure_is_logged_and_skipped(monkeypatch, logger, caplog):
    """A plugin whose __init__ raises is logged at ERROR and excluded from the cache."""
    registry = PluginRegistry(logger)
    # Bypass discovery — inject our broken class directly
    registry._classes = [_ExplodesOnInit]
    with caplog.at_level(logging.ERROR):
        instances = registry.all_instances()
    assert instances == []
    assert any(
        "_ExplodesOnInit" in record.message and "simulated init failure" in record.message
        for record in caplog.records
    )


class _OldStylePlugin:
    """Test fixture: only accepts cli_args, no config_manager (legacy shape)."""

    name = "oldstyle"
    priority = 999
    scan_type = "passive"

    def __init__(self, cli_args):
        self.cli_args = cli_args


def test_old_style_plugins_no_longer_load(logger, caplog):
    """Phase A5 removed the TypeError fallback — old-style plugins now fail.

    All v3 plugins use ``__init__(self, cli_args, config_manager=None)``.
    A plugin that still uses the legacy single-arg signature is treated as
    a broken plugin: its instantiation error is logged and it's excluded
    from the registry's cached instances.
    """
    registry = PluginRegistry(logger, config_manager=object())
    registry._classes = [_OldStylePlugin]
    with caplog.at_level(logging.ERROR):
        instances = registry.all_instances()
    assert instances == []
    assert any("_OldStylePlugin" in r.message for r in caplog.records)


# -- class-level identity (post-A5) ------------------------------------------


def test_plugin_classes_expose_name_as_class_attribute():
    """Phase A5: every plugin's ``name`` is a class attribute, readable
    without instantiation. Used by ConfigManager.collect_schemas_from_classes.
    """
    import logging
    registry = PluginRegistry(logging.getLogger("test"))
    for cls in registry.discover():
        # Read directly from the class — no instance involvement
        name = cls.__dict__.get("name") or getattr(cls, "name", None)
        assert name is not None, f"{cls.__name__} has no class-level name"
        assert isinstance(name, str) and name.strip(), (
            f"{cls.__name__}.name must be a non-empty string"
        )


def test_plugin_classes_expose_config_schema_as_class_attribute():
    """Phase A5: config_schema is a class attribute on every plugin."""
    import logging
    registry = PluginRegistry(logging.getLogger("test"))
    for cls in registry.discover():
        schema = getattr(cls, "config_schema", None)
        assert isinstance(schema, dict), (
            f"{cls.__name__}.config_schema must be a dict (got {type(schema).__name__})"
        )
