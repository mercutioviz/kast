"""Tests for kast.ai.http_adapter (Phase C8 kast-side hook)."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from kast.ai.base import AIConfigError, AIGenerationError
from kast.ai.http_adapter import HttpAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_urlopen(response_data: dict, status: int = 200):
    """Context manager mock for urllib.request.urlopen."""
    raw = json.dumps(response_data).encode()
    resp = MagicMock()
    resp.read.return_value = raw
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _valid_response():
    return {
        "text": '{"headline": "Test headline", "narrative": "Test narrative"}',
        "tokens_in": 150,
        "tokens_out": 250,
        "model": "claude-sonnet-4-6",
        "latency_ms": 980.0,
    }


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


def test_constructor_rejects_empty_url():
    with pytest.raises(AIConfigError):
        HttpAdapter(endpoint_url="")


def test_constructor_strips_trailing_slash():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000/")
    assert adapter._url == "http://localhost:5000"


def test_constructor_stores_token():
    adapter = HttpAdapter(endpoint_url="http://host", bearer_token="tok")
    assert adapter._token == "tok"


# ---------------------------------------------------------------------------
# generate — success path
# ---------------------------------------------------------------------------


def test_generate_success():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    mock_resp = _mock_urlopen(_valid_response())
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = adapter.generate(prompt="test prompt", system="sys")
    assert result.text == _valid_response()["text"]
    assert result.tokens_in == 150
    assert result.tokens_out == 250
    assert result.model == "claude-sonnet-4-6"
    assert result.latency_ms == 980.0


def test_generate_sends_correct_payload():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        captured["headers"] = dict(req.headers)
        return _mock_urlopen(_valid_response())

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        adapter.generate(prompt="my prompt", system="my system",
                         max_tokens=500, temperature=0.1)

    assert captured["url"] == "http://localhost:5000/api/ai/generate"
    assert captured["body"]["prompt"] == "my prompt"
    assert captured["body"]["system"] == "my system"
    assert captured["body"]["max_tokens"] == 500
    assert captured["body"]["temperature"] == 0.1
    assert captured["headers"].get("Content-type") == "application/json"


def test_generate_sends_bearer_token():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000", bearer_token="secret")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        return _mock_urlopen(_valid_response())

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        adapter.generate(prompt="x")

    assert captured["headers"].get("authorization") == "Bearer secret"


def test_generate_no_bearer_token_omits_auth_header():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["headers"] = {k.lower(): v for k, v in dict(req.headers).items()}
        return _mock_urlopen(_valid_response())

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        adapter.generate(prompt="x")

    assert "authorization" not in captured["headers"]


# ---------------------------------------------------------------------------
# generate — error paths
# ---------------------------------------------------------------------------


def test_generate_raises_on_http_error():
    import urllib.error
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    err = urllib.error.HTTPError(
        url="http://localhost:5000/api/ai/generate",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=BytesIO(b'{"error": "Insufficient credits"}'),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(AIGenerationError, match="403"):
            adapter.generate(prompt="x")


def test_generate_raises_on_http_error_extracts_message():
    import urllib.error
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    err = urllib.error.HTTPError(
        url="http://localhost:5000/api/ai/generate",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=BytesIO(b'{"error": "Rate limit exceeded"}'),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(AIGenerationError, match="Rate limit exceeded"):
            adapter.generate(prompt="x")


def test_generate_raises_on_url_error():
    import urllib.error
    adapter = HttpAdapter(endpoint_url="http://unreachable.invalid")
    err = urllib.error.URLError(reason="Name or service not known")
    with patch("urllib.request.urlopen", side_effect=err):
        with pytest.raises(AIGenerationError, match="Cannot reach AI endpoint"):
            adapter.generate(prompt="x")


def test_generate_raises_on_non_json_response():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    resp = MagicMock()
    resp.read.return_value = b"not json at all"
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=resp):
        with pytest.raises(AIGenerationError, match="non-JSON"):
            adapter.generate(prompt="x")


def test_generate_raises_on_error_field_in_response():
    adapter = HttpAdapter(endpoint_url="http://localhost:5000")
    mock_resp = _mock_urlopen({"error": "AI service unavailable"})
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(AIGenerationError, match="AI service unavailable"):
            adapter.generate(prompt="x")


# ---------------------------------------------------------------------------
# get_ai_adapter with endpoint_url
# ---------------------------------------------------------------------------


def test_get_ai_adapter_returns_http_adapter_when_endpoint_given():
    from kast.ai.config import get_ai_adapter
    from kast.ai.http_adapter import HttpAdapter as HA
    adapter = get_ai_adapter(endpoint_url="http://localhost:5000")
    assert isinstance(adapter, HA)


def test_get_ai_adapter_http_adapter_via_env(monkeypatch):
    monkeypatch.setenv("KAST_AI_ENDPOINT", "http://kast-web.local")
    from kast.ai.config import get_ai_adapter
    from kast.ai.http_adapter import HttpAdapter as HA
    adapter = get_ai_adapter()
    assert isinstance(adapter, HA)
    assert adapter._url == "http://kast-web.local"


def test_get_ai_adapter_endpoint_token_via_env(monkeypatch):
    monkeypatch.setenv("KAST_AI_ENDPOINT", "http://kast-web.local")
    monkeypatch.setenv("KAST_AI_ENDPOINT_TOKEN", "mytoken")
    from kast.ai.config import get_ai_adapter
    adapter = get_ai_adapter()
    assert adapter._token == "mytoken"


def test_get_ai_adapter_endpoint_takes_precedence_over_api_key(monkeypatch):
    monkeypatch.setenv("KAST_AI_ENDPOINT", "http://kast-web.local")
    monkeypatch.setenv("KAST_AI_API_KEY", "sk-test-key")
    from kast.ai.config import get_ai_adapter
    from kast.ai.http_adapter import HttpAdapter as HA
    # Should return HttpAdapter, not AnthropicAdapter, even though key is set
    adapter = get_ai_adapter()
    assert isinstance(adapter, HA)
