"""HTTP passthrough adapter — routes AI requests through the kast-web AI service.

This adapter is the kast-side contract for Phase C8.  When ``--ai-endpoint URL``
is supplied, kast forwards AI generation requests to the kast-web
``/api/ai/generate`` endpoint instead of calling the Anthropic API directly.
kast-web handles cost gating, API key management, and the review workflow on
its side; kast just receives a response in the standard ``AIResponse`` shape.

Expected request protocol (POST <endpoint>/api/ai/generate):
    Body (JSON):
        {
          "prompt":          <str>,
          "system":          <str>,
          "response_schema": <dict | null>,
          "max_tokens":      <int>,
          "temperature":     <float>
        }
    Headers:
        Content-Type: application/json
        Authorization: Bearer <token>   # if KAST_AI_ENDPOINT_TOKEN is set

Expected response protocol:
    Success (2xx):
        {
          "text":       <str>,
          "tokens_in":  <int>,
          "tokens_out": <int>,
          "model":      <str>,
          "latency_ms": <float>
        }
    Error:
        {"error": <str>}  — or any non-2xx HTTP status
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from kast.ai.base import AIConfigError, AIGenerationError, AIResponse


class HttpAdapter:
    """Forwards AI generation requests to a remote HTTP endpoint."""

    def __init__(self, endpoint_url: str, bearer_token: str | None = None, timeout: int = 90):
        if not endpoint_url:
            raise AIConfigError("HttpAdapter requires a non-empty endpoint_url")
        self._url = endpoint_url.rstrip("/")
        self._token = bearer_token
        self._timeout = timeout

    def generate(
        self,
        *,
        prompt: str,
        system: str = "",
        response_schema: dict | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.3,
    ) -> AIResponse:
        payload = {
            "prompt": prompt,
            "system": system,
            "response_schema": response_schema,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        req = urllib.request.Request(
            f"{self._url}/api/ai/generate",
            data=body,
            headers=headers,
            method="POST",
        )

        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read())
                msg = err_data.get("error", str(e))
            except Exception:
                msg = str(e)
            raise AIGenerationError(f"HTTP {e.code} from AI endpoint: {msg}") from e
        except urllib.error.URLError as e:
            raise AIGenerationError(
                f"Cannot reach AI endpoint {self._url}: {e.reason}"
            ) from e
        except Exception as e:
            raise AIGenerationError(
                f"Unexpected error calling AI endpoint {self._url}: {e}"
            ) from e

        local_latency_ms = (time.monotonic() - t0) * 1000

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise AIGenerationError(f"AI endpoint returned non-JSON response: {e}") from e

        if "error" in data:
            raise AIGenerationError(f"AI endpoint error: {data['error']}")

        return AIResponse(
            text=data.get("text", ""),
            tokens_in=int(data.get("tokens_in", 0)),
            tokens_out=int(data.get("tokens_out", 0)),
            model=str(data.get("model", "unknown")),
            latency_ms=float(data.get("latency_ms", local_latency_ms)),
            raw_response=data,
        )
