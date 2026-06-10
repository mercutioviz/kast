"""Tests for the v2-argv compatibility translator (Phase B7).

Pin down every v2 invocation pattern that kast-web and the v2 user
surface depends on. The translator runs in ``kast.cli.main()`` before
Click parses argv; if it ever drops a translation, the kast↔kast-web
contract documented in ``docs/web-integration.md`` breaks.
"""

from kast.cli import _translate_v2_argv

# -- pass-through cases ------------------------------------------------------


def test_empty_argv_passes_through():
    assert _translate_v2_argv([]) == []


def test_help_passes_through():
    assert _translate_v2_argv(["--help"]) == ["--help"]
    assert _translate_v2_argv(["-h"]) == ["-h"]


def test_v3_subcommand_passes_through_unchanged():
    """Already-v3 invocations (subcommand first) must not be touched."""
    assert _translate_v2_argv(["scan", "-t", "x.com"]) == ["scan", "-t", "x.com"]
    assert _translate_v2_argv(["plugins", "list", "--json"]) == ["plugins", "list", "--json"]
    assert _translate_v2_argv(["config", "show"]) == ["config", "show"]
    assert _translate_v2_argv(["version"]) == ["version"]


# -- v2 → v3 translations ----------------------------------------------------


def test_v2_version_flag_maps_to_version_subcommand():
    assert _translate_v2_argv(["--version"]) == ["version"]
    assert _translate_v2_argv(["-V"]) == ["version"]


def test_v2_list_plugins_maps_to_plugins_list():
    assert _translate_v2_argv(["--list-plugins"]) == ["plugins", "list"]
    assert _translate_v2_argv(["-ls"]) == ["plugins", "list"]


def test_v2_show_deps_maps_to_plugins_deps_with_other_flags_preserved():
    """--show-deps respects -m/--config/--set, so those must survive translation."""
    result = _translate_v2_argv(["--show-deps", "-m", "active"])
    assert result == ["plugins", "deps", "-m", "active"]

    result = _translate_v2_argv(["--show-deps", "--config", "/etc/kast/config.yaml"])
    assert result == ["plugins", "deps", "--config", "/etc/kast/config.yaml"]


def test_v2_config_init_maps_to_config_init():
    assert _translate_v2_argv(["--config-init"]) == ["config", "init"]


def test_v2_config_show_maps_to_config_show():
    assert _translate_v2_argv(["--config-show"]) == ["config", "show"]
    # With --config path argument
    assert _translate_v2_argv(["--config-show", "--config", "/x.yaml"]) == [
        "config", "show", "--config", "/x.yaml",
    ]


def test_v2_config_schema_maps_to_config_schema():
    assert _translate_v2_argv(["--config-schema"]) == ["config", "schema"]


# -- default scan fallback ---------------------------------------------------


def test_v2_target_only_becomes_scan():
    assert _translate_v2_argv(["--target", "example.com"]) == [
        "scan", "--target", "example.com",
    ]
    assert _translate_v2_argv(["-t", "example.com"]) == ["scan", "-t", "example.com"]


def test_v2_scan_with_options_translates_to_scan():
    """All scan-relevant flags carry through unchanged."""
    v2 = ["--target", "example.com", "--mode", "passive", "--parallel"]
    assert _translate_v2_argv(v2) == ["scan"] + v2


def test_v2_report_only_becomes_scan_report_only():
    """The kast↔kast-web contract: ``kast --report-only DIR`` is preserved
    by translating to ``kast scan --report-only DIR``. kast-web's task code
    uses this exact invocation; if this regresses, kast-web breaks.
    """
    v2 = ["--report-only", "/path/to/scan/dir"]
    assert _translate_v2_argv(v2) == ["scan"] + v2


def test_v2_scan_with_format_both():
    """The other kast-web invocation: scan + --format both."""
    v2 = ["-t", "example.com", "-m", "passive", "--format", "both"]
    assert _translate_v2_argv(v2) == ["scan"] + v2


# -- precedence -------------------------------------------------------------


def test_version_flag_takes_precedence_over_scan_flags():
    """v2 --version exits early before processing other flags. Translator
    matches this: hitting --version drops everything else."""
    result = _translate_v2_argv(["--version", "--target", "x.com"])
    assert result == ["version"]


def test_list_plugins_takes_precedence_over_scan_flags():
    result = _translate_v2_argv(["--list-plugins", "--mode", "active"])
    assert result == ["plugins", "list"]
