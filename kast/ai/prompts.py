"""Prompt loader for kast/ai/prompts/*.md.

Each prompt is a markdown file with YAML frontmatter and two body sections
delimited by ``## System`` and ``## User`` headers. The loader parses the
frontmatter, splits the body, and returns the system text, the user
template (Jinja2 source — caller renders), and the metadata dict.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml


PROMPTS_DIR = Path(__file__).parent / "prompts"

_FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)
_SECTION_RE = re.compile(r"^##\s+(System|User)\s*$", re.MULTILINE)


def load_prompt(name: str) -> tuple[str, str, dict]:
    """Load ``kast/ai/prompts/<name>.md`` and return (system, user_template, meta).

    Raises ``FileNotFoundError`` if the prompt file doesn't exist;
    ``ValueError`` if the file is missing frontmatter or section headers.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")

    content = path.read_text(encoding="utf-8")
    fm_match = _FRONTMATTER_RE.match(content)
    if not fm_match:
        raise ValueError(f"Prompt {name} is missing YAML frontmatter")

    metadata = yaml.safe_load(fm_match.group(1)) or {}
    body = fm_match.group(2)

    sections = _split_sections(body)
    if "System" not in sections or "User" not in sections:
        raise ValueError(f"Prompt {name} must contain '## System' and '## User' sections")

    return sections["System"].strip(), sections["User"].strip(), metadata


def _split_sections(body: str) -> dict[str, str]:
    """Split ``body`` into ``{section_name: content}`` keyed by ``## Header``."""
    splits = _SECTION_RE.split(body)
    # ``splits`` is [pre, header1, content1, header2, content2, ...]
    sections: dict[str, str] = {}
    for i in range(1, len(splits), 2):
        header = splits[i]
        content = splits[i + 1] if i + 1 < len(splits) else ""
        sections[header] = content
    return sections
