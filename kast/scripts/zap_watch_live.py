#!/usr/bin/env python3

import argparse
import json
import queue
import re as _re
import select
import sys
import termios
import threading
import time
import tty
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.layout import Layout
from rich import box

console = Console()

DEFAULT_URL = "http://localhost:8081"
DEFAULT_API_KEY = "kast3zap"

TERMINAL_STATUSES = {
    "stopped", "done", "complete", "completed", "finished", "100",
    "error", "failed", "aborted", "idle", "none",
}

_KEY_HINTS = (
    "[bold][Q][/bold]uit  "
    "[bold][R][/bold]eset alerts  "
    "[bold][D][/bold]iscover plans  "
    "[bold][C][/bold]lear history  "
    "[bold][P][/bold]ause  "
    "[bold][Space/F][/bold] Refresh"
)
_KEY_HINTS_PAUSED = (
    "[yellow bold][PAUSED][/yellow bold]  "
    "[bold][Q][/bold]uit  "
    "[bold][R][/bold]eset alerts  "
    "[bold][D][/bold]iscover plans  "
    "[bold][C][/bold]lear history  "
    "[bold][P][/bold] Resume  "
    "[bold][Space/F][/bold] Refresh"
)


# ---------------------------------------------------------------------------
# Key input thread
# ---------------------------------------------------------------------------

def _key_reader(
    key_queue: queue.Queue,
    stop_event: threading.Event,
    wakeup_event: threading.Event,
) -> None:
    """Read single keypresses from stdin and enqueue them. Runs in a daemon thread."""
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)  # immediate char delivery; Ctrl+C still raises SIGINT
        while not stop_event.is_set():
            if select.select([sys.stdin], [], [], 0.1)[0]:
                ch = sys.stdin.read(1)
                if ch:
                    key_queue.put(ch.lower())
                    wakeup_event.set()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


# ---------------------------------------------------------------------------
# ZAP API helpers
# ---------------------------------------------------------------------------

def build_url(base_url: str, path: str, apikey: str, params: dict | None = None) -> str:
    query = {"apikey": apikey}
    if params:
        query.update(params)
    return f"{base_url.rstrip('/')}{path}?{urllib.parse.urlencode(query)}"


def fetch_json(base_url: str, path: str, apikey: str, params: dict | None = None):
    url = build_url(base_url, path, apikey, params)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
            return {"_error": f"HTTP {e.code}", "_body": body}
        except Exception:
            return {"_error": f"HTTP {e.code}"}
    except Exception as e:
        return {"_error": str(e)}


def parse_int(value, default=None):
    if value is None:
        return default
    try:
        s = str(value).strip().replace("%", "")
        return int(float(s))
    except Exception:
        return default


def get_version(base_url: str, apikey: str):
    data = fetch_json(base_url, "/JSON/core/view/version/", apikey)
    if isinstance(data, dict) and "_error" not in data:
        return data.get("version", "unknown")
    return "unknown"


def get_alerts(base_url: str, apikey: str):
    num = fetch_json(base_url, "/JSON/core/view/numberOfAlerts/", apikey)
    total = 0
    if isinstance(num, dict) and "_error" not in num:
        total = parse_int(num.get("numberOfAlerts", num.get("alerts", 0)), 0) or 0
    summary = fetch_json(base_url, "/JSON/core/view/alertsSummary/", apikey)
    return total, _summarize_alerts(summary)


def delete_all_alerts(base_url: str, apikey: str) -> bool:
    data = fetch_json(base_url, "/JSON/core/action/deleteAllAlerts/", apikey)
    return isinstance(data, dict) and data.get("Result") == "OK"


def get_plan_progress(base_url: str, apikey: str, plan_id: int):
    """Returns None if the plan does not exist."""
    data = fetch_json(
        base_url, "/JSON/automation/view/planProgress/", apikey, {"planId": plan_id}
    )
    if not isinstance(data, dict) or "_error" in data or data.get("code") == "does_not_exist":
        return None
    return data


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def color_for_status(status: str) -> str:
    s = (status or "").lower()
    if s in {"running", "active", "in progress", "backlog"}:
        return "yellow"
    if s in {"stopped", "done", "complete", "completed", "finished", "100"}:
        return "green"
    if s in {"error", "failed", "aborted"}:
        return "red"
    if s in {"idle", "none"}:
        return "green"
    return "cyan"


def _summarize_alerts(summary_json):
    if not isinstance(summary_json, dict):
        return []
    data = summary_json.get("alertsSummary", summary_json.get("summary", summary_json))
    results = []
    if isinstance(data, dict):
        for k, v in data.items():
            if k.startswith("_"):
                continue
            results.append((str(k), parse_int(v, 0) or 0))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                sev = str(item.get("risk", item.get("name", "unknown")))
                count = parse_int(item.get("count", item.get("alerts", 0)), 0) or 0
                results.append((sev, count))
    order = {
        "High": 0, "high": 0, "Medium": 1, "medium": 1,
        "Low": 2, "low": 2, "Informational": 3, "informational": 3,
        "Info": 3, "info": 3, "Total": 9, "total": 9,
    }
    results.sort(key=lambda x: (order.get(x[0], 50), x[0].lower()))
    return results


def _parse_current_job(info: list) -> str:
    """Return the last job that started but hasn't finished yet."""
    running = None
    for msg in info:
        m = _re.match(r"Job (\S+) started", msg)
        if m:
            running = m.group(1)
        m = _re.match(r"Job (\S+) finished", msg)
        if m and running == m.group(1):
            running = None
    return running or ""


def is_plan_terminal(progress: dict) -> bool:
    """ZAP populates 'finished' when the plan is done; absence means still running."""
    return bool(progress.get("finished", ""))


def _plan_final_status(progress: dict) -> str:
    return "failed" if progress.get("error") else "completed"


def _plan_history_entry(pid: int, prog: dict) -> tuple[int, str, str]:
    finished_at = prog.get("finished", "")
    status = _plan_final_status(prog)
    name = f"Plan {pid} (finished {finished_at})" if finished_at else f"Plan {pid}"
    return (pid, name, status)


# ---------------------------------------------------------------------------
# Plan discovery and polling
# ---------------------------------------------------------------------------

def discover_plans(base_url: str, apikey: str, start_id: int = 0, miss_limit: int = 3):
    """
    Probe planIds sequentially from start_id until miss_limit consecutive misses.
    Returns (active_ids: set[int], historical: list[tuple[int, dict]]).
    """
    active_ids: set[int] = set()
    historical: list[tuple[int, dict]] = []
    misses = 0
    plan_id = start_id

    while misses < miss_limit:
        progress = get_plan_progress(base_url, apikey, plan_id)
        if progress is None:
            misses += 1
        else:
            misses = 0
            if is_plan_terminal(progress):
                historical.append((plan_id, progress))
            else:
                active_ids.add(plan_id)
        plan_id += 1

    return active_ids, historical


def poll_active_plans(base_url: str, apikey: str, active_plan_ids: set[int]):
    """
    Poll all known-active plan IDs.
    Returns (plan_jobs, newly_terminal, errors).
    """
    plan_jobs = []
    newly_terminal = []
    errors = []

    for plan_id in sorted(active_plan_ids):
        progress = get_plan_progress(base_url, apikey, plan_id)
        if progress is None:
            newly_terminal.append((plan_id, None))
            errors.append(f"automation plan {plan_id}: disappeared (ZAP restart?)")
            continue

        if is_plan_terminal(progress):
            newly_terminal.append((plan_id, progress))
        else:
            current_job = _parse_current_job(progress.get("info", []))
            warn_count = len(progress.get("warn", []))
            err_count = len(progress.get("error", []))
            details: dict = {"started": progress.get("started", ""), "current_job": current_job}
            if warn_count:
                details["warnings"] = warn_count
            if err_count:
                details["errors"] = err_count
            plan_jobs.append({
                "job": f"Automation Plan {plan_id}",
                "addon": "automation",
                "status": "running",
                "details": details,
            })

    return plan_jobs, newly_terminal, errors


def collect_jobs(base_url: str, apikey: str, spider_scan_ids: list[str]):
    """Collect non-automation jobs: ascan, spider, ajaxSpider, clientSpider, pscan."""
    jobs = []
    errors = []

    ascan = fetch_json(base_url, "/JSON/ascan/view/scans/", apikey)
    if isinstance(ascan, dict) and "_error" not in ascan:
        for scan in ascan.get("scans", []):
            if not isinstance(scan, dict):
                continue
            scan_id = scan.get("scanId", scan.get("id", ""))
            progress = parse_int(scan.get("progress", scan.get("status")), None)
            target = scan.get("url", scan.get("target", scan.get("name", "")))
            policy = scan.get("policy", scan.get("policyName", ""))
            if progress is None or progress < 100:
                jobs.append({
                    "job": "Active Scan", "addon": "ascan", "status": "running",
                    "details": {
                        "scanId": scan_id,
                        "progress": f"{progress}%" if progress is not None else "unknown",
                        "target": target, "policy": policy,
                    },
                })
    else:
        errors.append(
            f"ascan: {ascan.get('_error', 'unknown error') if isinstance(ascan, dict) else 'unknown error'}"
        )

    for scan_id in spider_scan_ids:
        spider = fetch_json(base_url, "/JSON/spider/view/status/", apikey, {"scanId": scan_id})
        if isinstance(spider, dict) and "_error" not in spider:
            pct = parse_int(spider.get("status"), None)
            if pct is None or pct < 100:
                jobs.append({
                    "job": "Spider", "addon": "spider", "status": "running",
                    "details": {"scanId": scan_id, "progress": f"{pct}%" if pct is not None else "unknown"},
                })
        else:
            errors.append(
                f"spider[{scan_id}]: {spider.get('_error', 'unknown error') if isinstance(spider, dict) else 'unknown error'}"
            )

    ajax = fetch_json(base_url, "/JSON/ajaxSpider/view/status/", apikey)
    if isinstance(ajax, dict) and "_error" not in ajax:
        status = str(ajax.get("status", "")).strip()
        if status.lower() == "running":
            jobs.append({
                "job": "Ajax Spider", "addon": "ajaxSpider", "status": status or "running",
                "details": {
                    "results": ajax.get("results", ajax.get("numberOfResults", "")),
                    "message": ajax.get("message", ""),
                },
            })
    else:
        errors.append(
            f"ajaxSpider: {ajax.get('_error', 'unknown error') if isinstance(ajax, dict) else 'unknown error'}"
        )

    client = fetch_json(base_url, "/JSON/clientSpider/view/status/", apikey)
    if isinstance(client, dict) and "_error" not in client:
        status = str(client.get("status", "")).strip()
        if status.lower() == "running":
            jobs.append({
                "job": "Client Spider", "addon": "clientSpider", "status": status or "running",
                "details": {
                    "results": client.get("results", client.get("numberOfResults", "")),
                    "message": client.get("message", ""),
                },
            })
    else:
        errors.append(
            f"clientSpider: {client.get('_error', 'unknown error') if isinstance(client, dict) else 'unknown error'}"
        )

    pscan = fetch_json(base_url, "/JSON/pscan/view/recordsToScan/", apikey)
    backlog = None
    if isinstance(pscan, dict) and "_error" not in pscan:
        backlog = (
            parse_int(pscan.get("recordsToScan", pscan.get("records", pscan.get("count"))), 0) or 0
        )
        if backlog > 0:
            jobs.append({
                "job": "Passive Scan", "addon": "pscan", "status": "backlog",
                "details": {"recordsToScan": backlog},
            })
    else:
        errors.append(
            f"pscan: {pscan.get('_error', 'unknown error') if isinstance(pscan, dict) else 'unknown error'}"
        )

    return jobs, errors, backlog


# ---------------------------------------------------------------------------
# Layout rendering
# ---------------------------------------------------------------------------

def render_layout(
    base_url: str,
    apikey: str,
    spider_scan_ids: list[str],
    jobs: list[dict],
    total_alerts: int,
    alert_summary: list[tuple[str, int]],
    historical_plans: list[tuple[int, str, str]],
    errors: list[str],
    poll_interval: int,
    last_poll: str,
    version: str,
    paused: bool = False,
    last_action: str | None = None,
):
    has_history = bool(historical_plans)
    layout = Layout()

    # Rich table height with show_lines=True and box.SQUARE:
    #   title(1) + top(1) + header(1) + header_sep(1) + N*row(N) + between_seps(N-1) + bottom(1)
    #   = 2N + 4
    footer_rows = 2 + min(len(errors), 3) + (1 if last_action else 0)
    footer_size = footer_rows * 2 + 4

    sections = [Layout(name="header", size=7), Layout(name="middle", ratio=2)]
    if has_history:
        history_size = min(len(historical_plans) * 2 + 4, 16)
        sections.append(Layout(name="history", size=history_size))
    sections.append(Layout(name="footer", size=footer_size))
    sections.append(Layout(name="keymenu", size=3))
    layout.split_column(*sections)

    # Header
    active_count = len(jobs)
    if paused:
        mode_str = "[yellow]PAUSED[/yellow]"
    elif active_count:
        mode_str = "[yellow]ACTIVE[/yellow]"
    else:
        mode_str = "[green]IDLE[/green]"

    header_text = (
        f"[bold]ZAP Watcher[/bold]\n"
        f"URL: {base_url}\n"
        f"Version: {version}\n"
        f"Mode: {mode_str}\n"
        f"Last poll: {last_poll}\n"
        f"Next poll: {'paused' if paused else f'{poll_interval}s'}\n"
        f"Spider IDs: {', '.join(spider_scan_ids) if spider_scan_ids else 'none'}"
    )
    layout["header"].update(Panel(header_text, title="Status", border_style="blue"))

    # Middle: jobs and alerts side by side
    layout["middle"].split_row(Layout(name="jobs"), Layout(name="alerts"))

    jobs_table = Table(title="Running Jobs", box=box.SQUARE, show_lines=True, expand=True)
    jobs_table.add_column("Job", style="bold")
    jobs_table.add_column("Addon")
    jobs_table.add_column("Status")
    jobs_table.add_column("Details", overflow="fold")

    if jobs:
        for job in jobs:
            color = color_for_status(job.get("status", ""))
            detail_str = ", ".join(
                f"{k}={v}" for k, v in job.get("details", {}).items() if v not in ("", None)
            )
            jobs_table.add_row(
                f"[{color}]{job.get('job', '')}[/{color}]",
                f"[{color}]{job.get('addon', '')}[/{color}]",
                f"[{color}]{job.get('status', '')}[/{color}]",
                f"[{color}]{detail_str}[/{color}]",
            )
    else:
        jobs_table.add_row(
            "[green]None[/green]", "[green]-[/green]",
            "[green]idle[/green]", "[green]No running scan jobs detected[/green]",
        )

    alerts_table = Table(title="Alerts", box=box.SQUARE, show_lines=True, expand=True)
    alerts_table.add_column("Metric", style="bold")
    alerts_table.add_column("Value", justify="right")
    alerts_table.add_row("Total alerts", str(total_alerts))
    for sev, count in alert_summary:
        color = {
            "High": "red", "Medium": "yellow", "Low": "green",
            "Informational": "cyan", "Info": "cyan",
        }.get(sev, "white")
        alerts_table.add_row(f"[{color}]{sev}[/{color}]", str(count))

    layout["middle"]["jobs"].update(jobs_table)
    layout["middle"]["alerts"].update(alerts_table)

    # Completed plans history
    if has_history:
        history_table = Table(
            title="Completed Automation Plans", box=box.SQUARE, show_lines=True, expand=True
        )
        history_table.add_column("Plan ID", style="bold", justify="right")
        history_table.add_column("Name")
        history_table.add_column("Final Status")
        for plan_id, plan_name, status in historical_plans:
            color = color_for_status(status)
            history_table.add_row(
                f"[{color}]{plan_id}[/{color}]",
                f"[{color}]{plan_name or f'Plan {plan_id}'}[/{color}]",
                f"[{color}]{status}[/{color}]",
            )
        layout["history"].update(history_table)

    # Diagnostics footer
    footer_table = Table(title="Diagnostics", box=box.SQUARE, show_lines=True, expand=True)
    footer_table.add_column("Item", style="bold")
    footer_table.add_column("Value", overflow="fold")
    footer_table.add_row("API Key", "[dim]hidden[/dim]")
    footer_table.add_row("Errors", str(len(errors)))
    for idx, err in enumerate(errors[:3], start=1):
        footer_table.add_row(f"Error {idx}", f"[red]{err}[/red]")
    if last_action:
        footer_table.add_row("Last action", f"[cyan]{last_action}[/cyan]")
    layout["footer"].update(footer_table)

    # Key menu
    hints = _KEY_HINTS_PAUSED if paused else _KEY_HINTS
    layout["keymenu"].update(Panel(hints, border_style="dim"))

    return layout


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Live watcher for a running ZAP instance using rich.live."
    )
    parser.add_argument("--url", default=DEFAULT_URL,
        help=f"ZAP base URL (default: {DEFAULT_URL})")
    parser.add_argument("--apikey", default=DEFAULT_API_KEY,
        help=f"ZAP API key (default: {DEFAULT_API_KEY})")
    parser.add_argument("--spider-scan-id", action="append", default=[],
        help="Traditional spider scan ID to watch. May be passed multiple times.")
    parser.add_argument("--plan-id", type=int, action="append", default=[],
        help=(
            "Automation plan ID to watch. May be passed multiple times. "
            "If omitted, plans are auto-discovered on startup."
        ))
    parser.add_argument("--idle-sleep", type=int, default=10,
        help="Seconds to sleep when no jobs are running (default: 10)")
    parser.add_argument("--active-sleep", type=int, default=3,
        help="Seconds to sleep when jobs are running (default: 3)")
    args = parser.parse_args()

    # Plan tracking state
    active_plan_ids: set[int] = set()
    historical_plans: list[tuple[int, str, str]] = []
    next_probe_id: int = 0
    explicit_plan_ids = bool(args.plan_id)

    if explicit_plan_ids:
        active_plan_ids = set(args.plan_id)
        next_probe_id = max(args.plan_id) + 1
    else:
        console.print("[dim]Discovering automation plans...[/dim]")
        found_active, found_historical = discover_plans(args.url, args.apikey)
        active_plan_ids = found_active
        for pid, prog in found_historical:
            historical_plans.append(_plan_history_entry(pid, prog))
        all_known = list(active_plan_ids) + [pid for pid, _, _ in historical_plans]
        next_probe_id = (max(all_known) + 1) if all_known else 0

    # Key input thread (only when stdin is a real terminal)
    key_queue: queue.Queue = queue.Queue()
    wakeup_event = threading.Event()
    stop_event = threading.Event()
    has_tty = sys.stdin.isatty()
    if has_tty:
        key_thread = threading.Thread(
            target=_key_reader, args=(key_queue, stop_event, wakeup_event), daemon=True
        )
        key_thread.start()

    # Display state preserved across pause cycles
    paused = False
    last_action: str | None = None
    all_jobs: list[dict] = []
    all_errors: list[str] = []
    total_alerts = 0
    alert_summary: list[tuple[str, int]] = []
    last_poll = "—"
    version = "—"
    poll_interval = args.idle_sleep

    def _now() -> str:
        return datetime.now().strftime("%H:%M:%S")

    try:
        with Live(console=console, refresh_per_second=4, screen=True) as live:
            while True:
                # --- Drain key queue ---
                skip_sleep = False
                try:
                    while True:
                        key = key_queue.get_nowait()
                        if key == "q":
                            raise KeyboardInterrupt
                        elif key == "r":
                            ok = delete_all_alerts(args.url, args.apikey)
                            last_action = f"Alerts reset at {_now()}" if ok else f"Alert reset failed at {_now()}"
                        elif key == "d":
                            active_plan_ids.clear()
                            historical_plans.clear()
                            next_probe_id = 0
                            last_action = f"Plan discovery reset at {_now()}"
                        elif key == "c":
                            historical_plans.clear()
                            last_action = f"History cleared at {_now()}"
                        elif key == "p":
                            paused = not paused
                            last_action = f"{'Paused' if paused else 'Resumed'} at {_now()}"
                        elif key in ("f", " "):
                            skip_sleep = True
                            paused = False
                except queue.Empty:
                    pass

                # --- Paused: re-render frozen display and wait for a keypress ---
                if paused:
                    layout = render_layout(
                        base_url=args.url, apikey=args.apikey,
                        spider_scan_ids=args.spider_scan_id,
                        jobs=all_jobs, total_alerts=total_alerts,
                        alert_summary=alert_summary,
                        historical_plans=historical_plans,
                        errors=all_errors, poll_interval=poll_interval,
                        last_poll=last_poll, version=version,
                        paused=True, last_action=last_action,
                    )
                    live.update(layout)
                    wakeup_event.wait(timeout=0.5)
                    wakeup_event.clear()
                    continue

                # --- Normal poll cycle ---
                version = get_version(args.url, args.apikey)

                # Probe for newly started plans
                if not explicit_plan_ids:
                    new_active, new_hist = discover_plans(
                        args.url, args.apikey, start_id=next_probe_id
                    )
                    if new_active or new_hist:
                        active_plan_ids |= new_active
                        for pid, prog in new_hist:
                            historical_plans.append(_plan_history_entry(pid, prog))
                        all_known = list(active_plan_ids) + [pid for pid, _, _ in historical_plans]
                        next_probe_id = max(all_known) + 1

                # Poll active plans
                plan_jobs, newly_terminal, plan_errors = poll_active_plans(
                    args.url, args.apikey, active_plan_ids
                )
                for plan_id, progress in newly_terminal:
                    active_plan_ids.discard(plan_id)
                    if progress is not None:
                        historical_plans.append(_plan_history_entry(plan_id, progress))
                    else:
                        historical_plans.append((plan_id, f"Plan {plan_id}", "gone"))

                jobs, errors, _backlog = collect_jobs(args.url, args.apikey, args.spider_scan_id)
                all_jobs = plan_jobs + jobs
                all_errors = plan_errors + errors

                total_alerts, alert_summary = get_alerts(args.url, args.apikey)
                last_poll = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                poll_interval = args.active_sleep if all_jobs else args.idle_sleep

                layout = render_layout(
                    base_url=args.url, apikey=args.apikey,
                    spider_scan_ids=args.spider_scan_id,
                    jobs=all_jobs, total_alerts=total_alerts,
                    alert_summary=alert_summary,
                    historical_plans=historical_plans,
                    errors=all_errors, poll_interval=poll_interval,
                    last_poll=last_poll, version=version,
                    paused=False, last_action=last_action,
                )
                live.update(layout)
                last_action = None  # shown for one poll cycle only

                # Interruptible sleep: any keypress wakes it early
                if not skip_sleep:
                    wakeup_event.wait(timeout=poll_interval)
                    wakeup_event.clear()

    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        console.print("\n[bold]Stopping watcher.[/bold]")


if __name__ == "__main__":
    main()
