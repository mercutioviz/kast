"""AnthropicAdapter — concrete AIAdapter for Claude (Anthropic SDK ≥ 0.97).

Uses the SDK's native ``output_config={"format": {"type": "json_schema",
"schema": {...}}}`` for structured output. The model returns a single text
block whose content is the JSON document — the caller parses it.
"""

from __future__ import annotations

import time
from typing import Any

from anthropic import Anthropic, APIError

from kast.ai.base import AIGenerationError, AIResponse


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_TIMEOUT_SECS = 60.0


class AnthropicAdapter:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        base_url: str | None = None,
    ):
        self.model = model
        client_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "timeout": DEFAULT_TIMEOUT_SECS,
        }
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = Anthropic(**client_kwargs)

    def generate(
        self,
        *,
        prompt: str,
        system: str = "",
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> AIResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        if response_schema is not None:
            kwargs["output_config"] = {
                "format": {"type": "json_schema", "schema": response_schema},
            }

        start = time.monotonic()
        try:
            resp = self._client.messages.create(**kwargs)
        except APIError as e:
            raise AIGenerationError(f"Anthropic API error: {e}") from e
        latency_ms = int((time.monotonic() - start) * 1000)

        text = _extract_text(resp)
        if not text:
            raise AIGenerationError("Anthropic response contained no text block")

        return AIResponse(
            text=text,
            tokens_in=resp.usage.input_tokens,
            tokens_out=resp.usage.output_tokens,
            model=resp.model,
            latency_ms=latency_ms,
            raw_response=resp.model_dump() if hasattr(resp, "model_dump") else None,
        )


def _extract_text(resp: Any) -> str:
    """Return the concatenated text from all text blocks in the response."""
    parts: list[str] = []
    for block in getattr(resp, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", ""))
    return "".join(parts)
