"""AI adapter resolution: env vars > ~/.config/kast/ai.yaml > AIConfigError.

Resolution order:
1. ``endpoint_url`` kwarg (or ``KAST_AI_ENDPOINT`` env var) → HttpAdapter
2. ``KAST_AI_API_KEY`` / ``~/.config/kast/ai.yaml`` → AnthropicAdapter
3. raise ``AIConfigError``
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
    endpoint_url: str | None = None,
) -> AIAdapter:
    """Resolve and construct an AI adapter.

    When ``endpoint_url`` is supplied (or ``KAST_AI_ENDPOINT`` env var is set),
    an ``HttpAdapter`` is returned and all API-key / provider logic is bypassed.
    The HTTP adapter routes AI requests to the kast-web AI service (Phase C8).

    Direct-API precedence (no endpoint):
    1. ``KAST_AI_API_KEY`` environment variable
    2. ``~/.config/kast/ai.yaml``  (``{provider, api_key, model}``)
    3. raise ``AIConfigError``

    ``KAST_AI_PROVIDER`` env var overrides ``adapter_name``;
    ``KAST_AI_MODEL`` env var overrides the resolved model unless
    ``model_override`` is supplied.
    """
    resolved_endpoint = endpoint_url or os.environ.get("KAST_AI_ENDPOINT")
    if resolved_endpoint:
        from kast.ai.http_adapter import HttpAdapter
        token = os.environ.get("KAST_AI_ENDPOINT_TOKEN")
        return HttpAdapter(endpoint_url=resolved_endpoint, bearer_token=token)

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
    base_url = os.environ.get("KAST_AI_BASE_URL") or file_cfg.get("base_url") or None

    if provider == "anthropic":
        from kast.ai.anthropic_adapter import DEFAULT_MODEL, AnthropicAdapter
        return AnthropicAdapter(
            api_key=api_key,
            model=model or DEFAULT_MODEL,
            base_url=base_url,
        )

    raise AIConfigError(f"Unknown AI provider: {provider!r}")


def _load_file_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise AIConfigError(f"Failed to parse {CONFIG_PATH}: {e}") from e
    return loaded if isinstance(loaded, dict) else {}
