"""kast.ai — AI adapter abstraction and integrations (Phase C1).

Provides a vendor-neutral ``AIAdapter`` Protocol with at least one concrete
implementation (Anthropic). High-level orchestration lives in
``kast.ai.summary``; configuration / credential resolution in
``kast.ai.config``.
"""

from kast.ai.base import AIAdapter, AIConfigError, AIGenerationError, AIResponse

__all__ = ["AIAdapter", "AIResponse", "AIConfigError", "AIGenerationError"]
