"""The katana version pin must agree across all three places that state it.

install.sh used to build katana from @latest, so a fresh box got whatever
shipped that day and two installs a week apart could crawl differently with
nothing recording why. The pin only holds if the installer, the plugin's
tested-against annotation, and the `kast doctor` install hints never drift
apart -- an install hint saying @latest quietly undoes the pin for anyone who
follows it.
"""

import re
from pathlib import Path

from kast.cli.doctor import EXTERNAL_TOOLS, KATANA_PINNED_VERSION, UPDATE_SPECS
from kast.plugins.katana_plugin import KatanaPlugin

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"


def _install_sh_pin() -> str:
    match = re.search(
        r'^KATANA_VERSION="([^"]+)"', INSTALL_SH.read_text(), re.MULTILINE
    )
    assert match, "install.sh no longer declares KATANA_VERSION"
    return match.group(1)


def test_installer_pins_the_tested_version():
    """A fresh install must produce the binary the plugin was tested against."""
    assert _install_sh_pin() == f"v{KatanaPlugin.tested_tool_version}"


def test_doctor_hint_version_matches_the_installer():
    assert KATANA_PINNED_VERSION == _install_sh_pin()


def test_installer_does_not_build_katana_from_latest():
    text = INSTALL_SH.read_text()
    assert "katana/cmd/katana@latest" not in text
    assert "katana/cmd/katana@${KATANA_VERSION}" in text


def test_no_doctor_hint_recommends_latest_katana():
    hints = [hint for binary, _, hint in EXTERNAL_TOOLS if binary == "katana"]
    hints += [s.update_hint for s in UPDATE_SPECS if s.binary == "katana"]
    assert hints, "katana lost its install/update hints"
    for hint in hints:
        assert "katana@latest" not in hint
        assert KATANA_PINNED_VERSION in hint
