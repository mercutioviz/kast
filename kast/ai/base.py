"""AIAdapter Protocol + shared types for kast.ai.

Subclasses don't inherit from a base class — the contract is a Protocol so
adapter implementations are decoupled from kast's internals. ``AIResponse``
is the wire-shape every adapter returns; ``AIGenerationError`` and
``AIConfigError`` are the only exceptions adapter code should raise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class AIConfigError(RuntimeError):
    """No usable AI configuration (missing API key, unknown adapter, etc.)."""


class AIGenerationError(RuntimeError):
    """The adapter call failed or returned an unusable response."""


@dataclass
class AIResponse:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int
    raw_response: dict[str, Any] | None = field(default=None, repr=False)


@runtime_checkable
class AIAdapter(Protocol):
    """Vendor-neutral generation interface.

    All adapters return an ``AIResponse``; on failure they raise
    ``AIGenerationError``. The optional ``response_schema`` requests
    structured JSON output (the adapter validates the response parses as
    JSON; the caller validates it matches the schema).
    """

    def generate(
        self,
        *,
        prompt: str,
        system: str = "",
        response_schema: dict[str, Any] | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> AIResponse: ...
