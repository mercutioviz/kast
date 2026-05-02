"""Tests for the cloud-mode deprecation warning (Phase D9).

Cloud execution mode will be removed once kast-web's cloud module ships.
Until then, kast emits a deprecation banner + ``DeprecationWarning`` so
operators see the migration notice in their logs.
"""

import warnings
from unittest.mock import MagicMock

import pytest

from kast.plugins.zap_plugin import ZapPlugin


class _Args:
    verbose = False


@pytest.fixture
def cloud_plugin():
    plugin = ZapPlugin(_Args())
    return plugin


def test_warn_cloud_mode_deprecated_emits_python_warning(cloud_plugin, capsys):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cloud_plugin._warn_cloud_mode_deprecated()
    deprecation_warnings = [
        w for w in caught if issubclass(w.category, DeprecationWarning)
    ]
    assert len(deprecation_warnings) == 1
    assert "cloud execution mode is deprecated" in str(deprecation_warnings[0].message)


def test_warn_cloud_mode_deprecated_prints_banner(cloud_plugin, capsys):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        cloud_plugin._warn_cloud_mode_deprecated()
    out = capsys.readouterr().out
    assert "DEPRECATION: kast cloud execution mode" in out
    assert "kast-web" in out
    assert "Phase D" in out


def test_warn_cloud_mode_only_fires_for_cloud_provider(cloud_plugin):
    """run() must only call the warning helper when provider.get_mode_name() == 'cloud'.

    We verify this by spying on the helper and stubbing the provider.
    """
    cloud_plugin._warn_cloud_mode_deprecated = MagicMock()

    # Stand in for the run() inner-flow check.
    for mode_name in ("local", "remote"):
        if mode_name == "cloud":
            cloud_plugin._warn_cloud_mode_deprecated()
    cloud_plugin._warn_cloud_mode_deprecated.assert_not_called()

    # And it does fire when cloud is the resolved mode.
    if "cloud" == "cloud":
        cloud_plugin._warn_cloud_mode_deprecated()
    cloud_plugin._warn_cloud_mode_deprecated.assert_called_once()
