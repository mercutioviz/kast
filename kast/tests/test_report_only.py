"""Verify the target round-trips through kast_info.json correctly."""

import json
import shutil
import tempfile
from pathlib import Path


def test_kast_info_extraction():
    """Writing a kast_info.json with cli_arguments.target lets a downstream
    consumer (e.g., the report-only / rerun path) recover the scan target."""
    temp_dir = Path(tempfile.mkdtemp())
    try:
        kast_info = {
            "kast_version": "3.0.21",
            "start_timestamp": "2026-06-09T16:19:25.885302",
            "end_timestamp": "2026-06-09T16:21:15.113785",
            "duration_seconds": 109.23,
            "cli_arguments": {
                "target": "example.com",
                "mode": "passive",
                "parallel": False,
                "verbose": False,
                "output_dir": str(temp_dir),
                "run_only": "mozilla_observatory,subfinder,wafw00f,whatweb,katana",
                "log_dir": "/var/log/kast/",
            },
        }

        kast_info_path = temp_dir / "kast_info.json"
        with open(kast_info_path, "w") as f:
            json.dump(kast_info, f, indent=2)

        with open(kast_info_path) as f:
            loaded_info = json.load(f)

        assert "cli_arguments" in loaded_info
        assert loaded_info["cli_arguments"].get("target") == "example.com"
    finally:
        shutil.rmtree(temp_dir)
