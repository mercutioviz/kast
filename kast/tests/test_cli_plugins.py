"""Tests for ``kast plugins`` subcommands (Phase B3).

Uses Click's CliRunner for in-process invocation. These tests exercise
the kast↔kast-web JSON contract: kast-web's admin would call
``kast plugins list --json`` and ``kast plugins show NAME --json``
to enumerate plugins and present per-plugin config UIs, replacing the
v2-era brittle parsing of Rich-rendered text (audit § 8).
"""

import json

from click.testing import CliRunner

from kast.cli.plugins import plugins as plugins_group


def test_plugins_list_default_format_succeeds():
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["list"])
    assert result.exit_code == 0, result.output
    assert "Available KAST Plugins" in result.output
    # At least one well-known plugin should appear
    assert "whatweb" in result.output


def test_plugins_list_json_returns_manifest():
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "kast_version" in payload
    assert "plugins" in payload
    assert len(payload["plugins"]) >= 10
    # Check the manifest schema kast-web depends on
    for entry in payload["plugins"]:
        for required_key in (
            "name", "display_name", "description",
            "scan_type", "priority", "available",
        ):
            assert required_key in entry


def test_plugins_show_known_plugin_succeeds():
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["show", "whatweb"])
    assert result.exit_code == 0, result.output
    assert "whatweb" in result.output
    assert "Configuration options" in result.output


def test_plugins_show_json_includes_config_schema():
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["show", "whatweb", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "whatweb"
    # config_schema is the kast-web payload for plugin-config UI generation
    assert "config_schema" in payload
    assert "properties" in payload["config_schema"]
    # WhatWeb's known config keys
    assert "aggression_level" in payload["config_schema"]["properties"]


def test_plugins_show_unknown_plugin_errors_helpfully():
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["show", "no_such_plugin"])
    # Click UsageError exits with code 2
    assert result.exit_code == 2
    assert "No plugin named" in result.output
    # Lists valid names so the user can correct their typo
    assert "Available plugin names:" in result.output
    assert "whatweb" in result.output


def test_plugins_show_active_plugin():
    """ZAP is the only active plugin; its show output should reflect that."""
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["show", "zap", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["scan_type"] == "active"


def test_plugins_show_dependencies_serialized():
    """ai_surface_detection has dependencies; they should appear in the JSON."""
    runner = CliRunner()
    result = runner.invoke(plugins_group, ["show", "ai_surface_detection", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    # ai_surface_detection depends on katana, whatweb, script_detection
    dep_names = {dep["plugin"] for dep in payload["dependencies"]}
    assert dep_names == {"katana", "whatweb", "script_detection"}
