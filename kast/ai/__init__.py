"""kast.ai — AI adapter abstraction and integrations.

Provides a vendor-neutral ``AIAdapter`` Protocol with concrete implementations
for Anthropic (direct API) and a kast-web HTTP passthrough. High-level
orchestration lives in ``kast.ai.summary``; configuration / credential
resolution in ``kast.ai.config``.
"""

from kast.ai.base import AIAdapter, AIConfigError, AIGenerationError, AIResponse

__all__ = ["AIAdapter", "AIResponse", "AIConfigError", "AIGenerationError"]
