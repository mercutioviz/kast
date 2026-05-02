"""Tests for kast.ai.prompts — frontmatter + section parsing."""

from pathlib import Path

import pytest

from kast.ai import prompts as prompts_mod


def test_load_real_exec_summary_v1():
    """The shipped v1 prompt loads and parses cleanly."""
    system, user, meta = prompts_mod.load_prompt("exec_summary_v1")
    assert "security analyst" in system.lower()
    assert "{{ target }}" in user
    assert meta["name"] == "exec_summary"
    assert meta["version"] == 1
    assert meta["default_model"] == "claude-sonnet-4-6"


def test_load_prompt_missing_raises_filenotfound():
    with pytest.raises(FileNotFoundError):
        prompts_mod.load_prompt("does_not_exist")


def _write_prompt(tmp_path, body):
    path = tmp_path / "test_prompt.md"
    path.write_text(body)
    return path


def test_no_frontmatter_raises(tmp_path, monkeypatch):
    p = _write_prompt(tmp_path, "## System\nhi\n## User\nthere\n")
    monkeypatch.setattr(prompts_mod, "PROMPTS_DIR", tmp_path)
    with pytest.raises(ValueError, match="missing YAML frontmatter"):
        prompts_mod.load_prompt("test_prompt")


def test_missing_section_raises(tmp_path, monkeypatch):
    p = _write_prompt(tmp_path, "---\nversion: 1\n---\n## System\nhi\n")
    monkeypatch.setattr(prompts_mod, "PROMPTS_DIR", tmp_path)
    with pytest.raises(ValueError, match="must contain '## System' and '## User'"):
        prompts_mod.load_prompt("test_prompt")


def test_sections_split_correctly(tmp_path, monkeypatch):
    p = _write_prompt(
        tmp_path,
        "---\nname: t\nversion: 1\n---\n\n## System\n\nA system message.\n\n## User\n\nA user message with {{ target }}.\n",
    )
    monkeypatch.setattr(prompts_mod, "PROMPTS_DIR", tmp_path)
    system, user, meta = prompts_mod.load_prompt("test_prompt")
    assert system == "A system message."
    assert user == "A user message with {{ target }}."
    assert meta["name"] == "t"
