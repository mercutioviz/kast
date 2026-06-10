"""Tests for ConfigManager.collect_schemas_from_classes.

The new path lets ``kast --config-schema`` enumerate every plugin's schema
without instantiating the plugins. These tests pin down the contract:
schema collection reads class attributes only and does not touch instances.
"""

import logging

import pytest

from kast.config_manager import ConfigManager


@pytest.fixture
def cm():
    return ConfigManager(logger=logging.getLogger("test.cm"))


class _GoodPlugin:
    """Test fixture: properly declares name + config_schema as class attrs."""
    name = "good"
    config_schema = {
        "type": "object",
        "title": "Good Plugin",
        "properties": {"x": {"type": "integer", "default": 1}},
    }


class _PluginWithoutSchema:
    """Test fixture: missing config_schema."""
    name = "no_schema"


class _PluginWithoutName:
    """Test fixture: missing name."""
    config_schema = {"type": "object", "title": "Anonymous"}


def test_collect_schemas_registers_well_formed_plugin(cm):
    cm.collect_schemas_from_classes([_GoodPlugin])
    assert "good" in cm.plugin_schemas
    assert cm.plugin_schemas["good"] == _GoodPlugin.config_schema


def test_collect_schemas_skips_plugin_without_schema(cm, caplog):
    with caplog.at_level(logging.WARNING):
        cm.collect_schemas_from_classes([_PluginWithoutSchema])
    assert "no_schema" not in cm.plugin_schemas
    assert any(
        "_PluginWithoutSchema" in r.message and "schema" in r.message.lower()
        for r in caplog.records
    )


def test_collect_schemas_skips_plugin_without_name(cm, caplog):
    with caplog.at_level(logging.WARNING):
        cm.collect_schemas_from_classes([_PluginWithoutName])
    assert len(cm.plugin_schemas) == 0


def test_collect_schemas_does_not_instantiate(cm):
    """Critical contract: classes are not instantiated."""
    instantiated = []

    class _ExplodesIfInstantiated:
        name = "explodes"
        config_schema = {"type": "object", "title": "Explodes"}

        def __init__(self, *args, **kwargs):
            instantiated.append(True)
            raise RuntimeError("collect_schemas_from_classes must not call __init__")

    cm.collect_schemas_from_classes([_ExplodesIfInstantiated])
    assert instantiated == [], "collect_schemas_from_classes must not instantiate"
    assert "explodes" in cm.plugin_schemas


def test_collect_schemas_handles_real_plugins():
    """End-to-end: every real kast plugin registers via class-attribute read."""
    from kast.registry import PluginRegistry
    cm = ConfigManager(logger=logging.getLogger("test.real"))
    registry = PluginRegistry(logging.getLogger("test.real"))
    cm.collect_schemas_from_classes(registry.discover())

    # At least 13 plugins should have schemas registered (grows as plugins are added)
    assert len(cm.plugin_schemas) >= 13
    # Sanity: well-known plugin names are present
    assert "whatweb" in cm.plugin_schemas
    assert "zap" in cm.plugin_schemas
    assert "testssl" in cm.plugin_schemas
    # And no plugin instances were created
    assert len(registry._instances) == 0
