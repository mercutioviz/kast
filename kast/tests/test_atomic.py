"""Tests for kast.core.atomic.write_json_atomic.

These pin down the contract enshrined in docs/web-integration.md
(state-bearing files must appear atomically).
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from kast.core.atomic import write_json_atomic


def test_writes_target_file(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic(target, {"plugin": "whatweb", "findings": 3})
    assert target.exists()
    assert json.loads(target.read_text()) == {"plugin": "whatweb", "findings": 3}


def test_default_indent_is_2(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic(target, {"a": 1})
    text = target.read_text()
    assert '  "a": 1' in text  # 2-space indented


def test_indent_can_be_overridden(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic(target, {"a": 1}, indent=None)
    assert target.read_text() == '{"a": 1}'


def test_default_kwarg_for_non_serializable(tmp_path):
    """The `default=str` kwarg path is supported (used by org_discovery)."""
    target = tmp_path / "out.json"

    class HasStr:
        def __str__(self):
            return "stringified"

    write_json_atomic(target, {"obj": HasStr()}, default=str)
    assert json.loads(target.read_text()) == {"obj": "stringified"}


def test_replaces_existing_file(tmp_path):
    target = tmp_path / "out.json"
    target.write_text('{"old": true}')
    write_json_atomic(target, {"new": True})
    assert json.loads(target.read_text()) == {"new": True}


def test_temp_file_does_not_persist_on_success(tmp_path):
    target = tmp_path / "out.json"
    write_json_atomic(target, {"ok": True})
    assert target.exists()
    assert not Path(f"{target}.tmp").exists()


def test_temp_file_cleaned_up_on_serialization_failure(tmp_path):
    """Non-serializable data raises but leaves no <path>.tmp behind."""
    target = tmp_path / "out.json"

    class NotSerializable:
        pass

    with pytest.raises(TypeError):
        write_json_atomic(target, {"bad": NotSerializable()})

    assert not target.exists()
    assert not Path(f"{target}.tmp").exists()


def test_uses_os_replace_for_atomicity(tmp_path):
    """Verify os.replace (atomic rename) is the mechanism, not a plain copy."""
    target = tmp_path / "out.json"
    with patch("kast.core.atomic.os.replace") as mock_replace:
        write_json_atomic(target, {"data": 1})
        assert mock_replace.called
        args = mock_replace.call_args.args
        assert str(args[0]).endswith("out.json.tmp")
        assert str(args[1]).endswith("out.json")


def test_existing_file_preserved_when_serialization_fails(tmp_path):
    """If the new write fails, the existing target is unchanged.

    This is the core atomicity property a kast-web watcher depends on.
    """
    target = tmp_path / "out.json"
    target.write_text('{"existing": true}')

    class NotSerializable:
        pass

    with pytest.raises(TypeError):
        write_json_atomic(target, {"bad": NotSerializable()})

    # Original file is untouched.
    assert json.loads(target.read_text()) == {"existing": True}


def test_accepts_str_path(tmp_path):
    target = str(tmp_path / "out.json")
    write_json_atomic(target, {"ok": True})
    assert Path(target).exists()


def test_accepts_pathlike(tmp_path):
    target = tmp_path / "out.json"  # PosixPath
    write_json_atomic(target, {"ok": True})
    assert target.exists()
