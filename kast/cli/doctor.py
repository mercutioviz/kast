"""``kast doctor`` (Phase B5) — environment health check.

Pre-flight check meant for an SA setting up a fresh kast install (or
diagnosing why a scan failed). Reports each check's status as one of:

- ``ok``      pass (green ✓)
- ``warn``    soft fail; kast still works but not at full capability (yellow ⚠)
- ``fail``    hard fail; something kast depends on is missing or broken (red ✗)
- ``info``    neutral note (cyan ℹ)

Exit code:
- 0 if no ``fail`` results
- 1 if any ``fail`` (CI-friendly)

Future B5+ work could add a ``--fix`` flag that attempts apt-installable
items; for now, every failure includes a concrete remediation hint.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import click
from rich.console import Console
from rich.table import Table

console = Console()


# Status enum (string-based for easy serialization).
OK, WARN, FAIL, INFO = "ok", "warn", "fail", "info"

_STATUS_MARKERS = {
    OK: "[green]✓[/green]",
    WARN: "[yellow]⚠[/yellow]",
    FAIL: "[red]✗[/red]",
    INFO: "[cyan]ℹ[/cyan]",
}


@dataclass
class CheckResult:
    """One row in the doctor report."""
    section: str
    name: str
    status: str  # one of OK/WARN/FAIL/INFO
    detail: str = ""
    hint: str = ""


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


MIN_PYTHON = (3, 9)


def check_python_version() -> CheckResult:
    cur = sys.version_info[:3]
    detail = f"Python {cur[0]}.{cur[1]}.{cur[2]}"
    if cur >= MIN_PYTHON:
        return CheckResult(
            section="Python Runtime",
            name="Python version",
            status=OK,
            detail=f"{detail} (>= {MIN_PYTHON[0]}.{MIN_PYTHON[1]} required)",
        )
    return CheckResult(
        section="Python Runtime",
        name="Python version",
        status=FAIL,
        detail=detail,
        hint=f"kast requires Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+; upgrade your interpreter.",
    )


REQUIRED_MODULES = [
    "rich", "click", "jinja2", "weasyprint", "requests",
    "yaml", "bs4", "tldextract",
]


def check_python_modules() -> List[CheckResult]:
    results = []
    for mod in REQUIRED_MODULES:
        try:
            __import__(mod)
            results.append(CheckResult("Python Modules", mod, OK))
        except ImportError as e:
            results.append(
                CheckResult(
                    section="Python Modules",
                    name=mod,
                    status=FAIL,
                    detail=str(e),
                    hint="pip install -r requirements.txt",
                )
            )
    return results


# Tool binary checks: (tool, plugin_name, install_hint)
EXTERNAL_TOOLS = [
    ("whatweb",    "whatweb",       "sudo apt install whatweb"),
    ("wafw00f",    "wafw00f",       "sudo apt install wafw00f  (or: pip install wafw00f)"),
    ("testssl.sh", "testssl",       "sudo apt install testssl.sh"),
    ("subfinder",  "subfinder",     "go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"),
    ("katana",     "katana",        "go install github.com/projectdiscovery/katana/cmd/katana@latest"),
    ("httpx",      "related_sites", "go install github.com/projectdiscovery/httpx/cmd/httpx@latest"),
    ("docker",     "zap (local)",   "https://docs.docker.com/engine/install/ — needed only for ZAP local mode"),
]


def check_external_tools() -> List[CheckResult]:
    results = []
    for binary, plugin_name, hint in EXTERNAL_TOOLS:
        path = shutil.which(binary)
        if path:
            results.append(
                CheckResult(
                    section="External Tool Binaries",
                    name=binary,
                    status=OK,
                    detail=path,
                )
            )
        else:
            # docker missing is WARN (only ZAP local-mode needs it); others are
            # WARN too because each plugin checks its own binary at runtime, so
            # a missing tool just disables one plugin rather than breaking kast.
            results.append(
                CheckResult(
                    section="External Tool Binaries",
                    name=binary,
                    status=WARN,
                    detail=f"not in PATH (used by: {plugin_name})",
                    hint=hint,
                )
            )
    return results


def check_log_dir_writable(log_dir: str = "/var/log/kast/") -> CheckResult:
    """Verify the log dir exists and is writable, or can be created."""
    p = Path(log_dir).expanduser()
    try:
        p.mkdir(parents=True, exist_ok=True)
        if os.access(str(p), os.W_OK):
            return CheckResult(
                section="Filesystem Permissions",
                name=f"log dir ({p})",
                status=OK,
                detail="writable",
            )
        return CheckResult(
            section="Filesystem Permissions",
            name=f"log dir ({p})",
            status=WARN,
            detail="exists but not writable by current user",
            hint=f"sudo chown $USER {p}  # or sudo chmod 775 {p}",
        )
    except PermissionError:
        return CheckResult(
            section="Filesystem Permissions",
            name=f"log dir ({p})",
            status=WARN,
            detail="cannot create — using --log-dir at scan time falls back to a different path",
            hint=f"sudo mkdir -p {p} && sudo chown $USER {p}",
        )


def check_results_dir() -> CheckResult:
    """Default results dir is ~/kast_results — must be creatable."""
    p = Path.home() / "kast_results"
    try:
        p.mkdir(parents=True, exist_ok=True)
        return CheckResult(
            section="Filesystem Permissions",
            name=f"results dir ({p})",
            status=OK,
            detail="writable",
        )
    except OSError as e:
        return CheckResult(
            section="Filesystem Permissions",
            name=f"results dir ({p})",
            status=FAIL,
            detail=str(e),
            hint="Pass an alternate path via --output-dir <path> on each scan.",
        )


CONFIG_SEARCH_PATHS = [
    Path("./kast_config.yaml"),
    Path.home() / ".config" / "kast" / "config.yaml",
    Path("/etc/kast/config.yaml"),
]


def check_config_files() -> List[CheckResult]:
    """Each config search path: present + valid YAML, or absent."""
    import yaml as yaml_mod

    results = []
    found_any = False
    for path in CONFIG_SEARCH_PATHS:
        path = path.expanduser()
        if not path.exists():
            continue
        found_any = True
        try:
            with open(path) as f:
                yaml_mod.safe_load(f)
            results.append(
                CheckResult(
                    section="Configuration",
                    name=str(path),
                    status=OK,
                    detail="valid YAML",
                )
            )
        except yaml_mod.YAMLError as e:
            results.append(
                CheckResult(
                    section="Configuration",
                    name=str(path),
                    status=FAIL,
                    detail=f"YAML parse error: {e}",
                    hint="Fix the YAML syntax. `kast config init` writes a known-good default.",
                )
            )
    if not found_any:
        results.append(
            CheckResult(
                section="Configuration",
                name="kast_config.yaml",
                status=INFO,
                detail="no config file found at any search path; kast will use defaults",
                hint="Run `kast config init` to create one.",
            )
        )
    return results


def check_issue_registry() -> CheckResult:
    """Issue registry must load and parse."""
    registry_path = Path(__file__).resolve().parent.parent / "data" / "issue_registry.json"
    if not registry_path.exists():
        return CheckResult(
            section="Issue Registry",
            name=str(registry_path),
            status=FAIL,
            detail="not found",
            hint="kast install is incomplete — re-run install.sh or git checkout the file.",
        )
    try:
        data = json.loads(registry_path.read_text())
        return CheckResult(
            section="Issue Registry",
            name=str(registry_path),
            status=OK,
            detail=f"valid JSON, {len(data)} entries",
        )
    except json.JSONDecodeError as e:
        return CheckResult(
            section="Issue Registry",
            name=str(registry_path),
            status=FAIL,
            detail=f"JSON parse error: {e}",
            hint="`git checkout kast/data/issue_registry.json` to restore.",
        )


def check_plugin_loading() -> List[CheckResult]:
    """Every plugin class instantiates without exception."""
    from kast.registry import PluginRegistry

    log = logging.getLogger("kast.doctor")
    log.addHandler(logging.NullHandler())

    registry = PluginRegistry(log)
    classes = registry.discover()
    instances = registry.all_instances()

    results = [
        CheckResult(
            section="Plugin Loading",
            name="discover",
            status=OK,
            detail=f"{len(classes)} plugin class(es) found",
        ),
        CheckResult(
            section="Plugin Loading",
            name="instantiate",
            status=OK if len(instances) == len(classes) else FAIL,
            detail=f"{len(instances)}/{len(classes)} instantiated",
            hint=(
                "Run with -v to see per-plugin errors logged to console."
                if len(instances) != len(classes) else ""
            ),
        ),
    ]
    return results


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


CHECKS: List[Callable[[], CheckResult | List[CheckResult]]] = [
    check_python_version,
    check_python_modules,
    check_external_tools,
    check_log_dir_writable,
    check_results_dir,
    check_config_files,
    check_issue_registry,
    check_plugin_loading,
]


def run_all_checks() -> List[CheckResult]:
    """Run every check and return a flat list of CheckResult."""
    out: List[CheckResult] = []
    for check in CHECKS:
        result = check()
        if isinstance(result, list):
            out.extend(result)
        else:
            out.append(result)
    return out


def render_report(results: List[CheckResult]) -> None:
    """Print a Rich table grouped by section."""
    sections: dict[str, List[CheckResult]] = {}
    for r in results:
        sections.setdefault(r.section, []).append(r)

    for section, items in sections.items():
        table = Table(title=section, title_style="bold cyan", show_lines=False, expand=True)
        table.add_column("", width=2)
        table.add_column("Check", style="bold")
        table.add_column("Detail")
        table.add_column("Hint", style="dim")

        for item in items:
            table.add_row(
                _STATUS_MARKERS.get(item.status, " "),
                item.name,
                item.detail,
                item.hint,
            )
        console.print(table)
        console.print()


def render_summary(results: List[CheckResult]) -> dict:
    """Print and return a one-line summary; counts by status."""
    counts = {OK: 0, WARN: 0, FAIL: 0, INFO: 0}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    parts = []
    if counts[OK]:
        parts.append(f"[green]{counts[OK]} ok[/green]")
    if counts[WARN]:
        parts.append(f"[yellow]{counts[WARN]} warning[/yellow]")
    if counts[FAIL]:
        parts.append(f"[red]{counts[FAIL]} failure[/red]")
    if counts[INFO]:
        parts.append(f"[cyan]{counts[INFO]} info[/cyan]")
    summary = ", ".join(parts) if parts else "no checks ran"
    console.print(f"[bold]Summary:[/bold] {summary}")
    return counts


# ---------------------------------------------------------------------------
# Click command
# ---------------------------------------------------------------------------


@click.command()
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted tables.")
def doctor(json_output: bool) -> None:
    """Run environment health checks (Python, tools, perms, plugins)."""
    results = run_all_checks()

    if json_output:
        payload = {
            "results": [
                {
                    "section": r.section,
                    "name": r.name,
                    "status": r.status,
                    "detail": r.detail,
                    "hint": r.hint,
                }
                for r in results
            ],
            "summary": {
                status: sum(1 for r in results if r.status == status)
                for status in (OK, WARN, FAIL, INFO)
            },
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        console.print()
        console.print("[bold cyan]KAST Environment Check[/bold cyan]\n")
        render_report(results)
        counts = render_summary(results)
        if counts[FAIL]:
            console.print(
                "\n[red]One or more checks failed; "
                "follow the hints above to remediate.[/red]"
            )

    # Exit code reflects fail count for CI-friendliness.
    fail_count = sum(1 for r in results if r.status == FAIL)
    if fail_count:
        sys.exit(1)
