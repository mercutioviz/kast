"""Tests for ConfigManager.collect_schemas_from_classes.

The new path lets ``kast --config-schema`` enumerate every plugin's schema
without instantiating the plugins. These tests pin down the contract:
schema collection reads class attributes only and does not touch instances.
"""

import logging

import pytest
import yaml

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


# -- create_default_config ---------------------------------------------------
#
# Generated configs must not freeze schema defaults. Writing them live meant a
# later change to a default never reached a machine that had ever run
# `kast config init` -- katana kept crawling unbounded after it gained a 300s
# budget, with nothing on the box saying why.


def test_create_default_config_comments_out_defaults(cm, tmp_path):
    cm.collect_schemas_from_classes([_GoodPlugin])
    path = tmp_path / "config.yaml"
    cm.create_default_config(str(path))

    text = path.read_text()
    assert "# plugins:" in text
    assert "#   good:" in text
    assert "#     x: 1" in text
    # The only live key is the version marker.
    assert yaml.safe_load(text) == {"kast": {"config_version": cm.CONFIG_VERSION}}


def test_generated_config_does_not_override_schema_defaults(cm, tmp_path):
    """Round-trip: loading a generated file still yields the schema default."""
    cm.collect_schemas_from_classes([_GoodPlugin])
    path = tmp_path / "config.yaml"
    cm.create_default_config(str(path))

    # A later release bumps the default; the generated file must not pin the old one.
    fresh = ConfigManager(logger=logging.getLogger("test.fresh"))
    fresh.register_plugin_schema("good", {
        "type": "object",
        "properties": {"x": {"type": "integer", "default": 99}},
    })
    fresh.load(str(path))

    assert fresh.get_plugin_config("good")["x"] == 99


def test_create_default_config_round_trips_through_real_schemas(tmp_path):
    """The real generated file must parse and leave every plugin on its default."""
    from kast.registry import PluginRegistry

    log = logging.getLogger("test.roundtrip")
    cm = ConfigManager(logger=log)
    cm.collect_schemas_from_classes(PluginRegistry(log).discover())
    path = tmp_path / "config.yaml"
    cm.create_default_config(str(path))

    fresh = ConfigManager(logger=log)
    fresh.collect_schemas_from_classes(PluginRegistry(log).discover())
    fresh.load(str(path))

    katana = fresh.get_plugin_config("katana")
    assert katana["crawl_duration"] == 300
    assert katana["report_scope"] == "organization"
