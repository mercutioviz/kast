"""AI adapter resolution: env vars > ~/.config/kast/ai.yaml > AIConfigError.

For Phase C1 (kast CLI direct), only the Anthropic adapter is wired.
The kast-web passthrough endpoint (``--ai-endpoint``) is C8 and not
implemented here.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from kast.ai.base import AIAdapter, AIConfigError


CONFIG_PATH = Path.home() / ".config" / "kast" / "ai.yaml"


def get_ai_adapter(
    adapter_name: str = "anthropic",
    model_override: str | None = None,
) -> AIAdapter:
    """Resolve and construct an AI adapter.

    Precedence:
    1. ``KAST_AI_API_KEY`` environment variable
    2. ``~/.config/kast/ai.yaml``  (``{provider, api_key, model}``)
    3. raise ``AIConfigError``

    ``KAST_AI_PROVIDER`` env var overrides ``adapter_name``;
    ``KAST_AI_MODEL`` env var overrides the resolved model unless
    ``model_override`` is supplied.
    """
    file_cfg = _load_file_config()
    provider = (
        os.environ.get("KAST_AI_PROVIDER")
        or file_cfg.get("provider")
        or adapter_name
    )
    api_key = os.environ.get("KAST_AI_API_KEY") or file_cfg.get("api_key")
    if not api_key:
        raise AIConfigError(
            "No AI API key found. Set KAST_AI_API_KEY or configure "
            f"{CONFIG_PATH}."
        )

    model = (
        model_override
        or os.environ.get("KAST_AI_MODEL")
        or file_cfg.get("model")
    )

    if provider == "anthropic":
        from kast.ai.anthropic_adapter import AnthropicAdapter, DEFAULT_MODEL
        return AnthropicAdapter(api_key=api_key, model=model or DEFAULT_MODEL)

    raise AIConfigError(f"Unknown AI provider: {provider!r}")


def _load_file_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise AIConfigError(f"Failed to parse {CONFIG_PATH}: {e}") from e
    return loaded if isinstance(loaded, dict) else {}
