"""Tests for kast.ai.anthropic_adapter — mocked Anthropic SDK calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from anthropic import APIError

from kast.ai import AIGenerationError
from kast.ai.anthropic_adapter import AnthropicAdapter, _extract_text


def _make_response(text="hello", tokens_in=10, tokens_out=20, model="claude-sonnet-4-6"):
    """Build a minimal mock that mimics anthropic's Message response."""
    block = SimpleNamespace(type="text", text=text)
    return SimpleNamespace(
        content=[block],
        usage=SimpleNamespace(input_tokens=tokens_in, output_tokens=tokens_out),
        model=model,
        model_dump=lambda: {"id": "msg_test"},
    )


def test_generate_success_returns_ai_response():
    adapter = AnthropicAdapter(api_key="test-key", model="claude-sonnet-4-6")
    mock_resp = _make_response(text='{"headline": "x", "narrative": "y"}',
                               tokens_in=42, tokens_out=17)
    with patch.object(adapter._client.messages, "create", return_value=mock_resp) as mock_create:
        result = adapter.generate(prompt="hi", system="you are helpful")

    assert result.text == '{"headline": "x", "narrative": "y"}'
    assert result.tokens_in == 42
    assert result.tokens_out == 17
    assert result.model == "claude-sonnet-4-6"
    assert result.latency_ms >= 0
    # System and prompt threaded through
    kwargs = mock_create.call_args.kwargs
    assert kwargs["system"] == "you are helpful"
    assert kwargs["messages"][0]["content"] == "hi"
    # No structured-output config when response_schema is None
    assert "output_config" not in kwargs


def test_generate_with_response_schema_sets_output_config():
    adapter = AnthropicAdapter(api_key="test-key")
    mock_resp = _make_response(text='{"headline": "h", "narrative": "n"}')
    schema = {"type": "object", "properties": {"headline": {"type": "string"}}}
    with patch.object(adapter._client.messages, "create", return_value=mock_resp) as mock_create:
        adapter.generate(prompt="x", response_schema=schema)

    kwargs = mock_create.call_args.kwargs
    assert kwargs["output_config"] == {
        "format": {"type": "json_schema", "schema": schema}
    }


def test_generate_maps_api_error_to_ai_generation_error():
    adapter = AnthropicAdapter(api_key="test-key")
    err = APIError("upstream is sad", request=MagicMock(), body=None)
    with patch.object(adapter._client.messages, "create", side_effect=err):
        with pytest.raises(AIGenerationError, match="Anthropic API error"):
            adapter.generate(prompt="x")


def test_generate_rejects_empty_response():
    adapter = AnthropicAdapter(api_key="test-key")
    empty = SimpleNamespace(
        content=[],
        usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        model="m",
        model_dump=lambda: {},
    )
    with patch.object(adapter._client.messages, "create", return_value=empty):
        with pytest.raises(AIGenerationError, match="no text block"):
            adapter.generate(prompt="x")


def test_extract_text_concatenates_text_blocks():
    resp = SimpleNamespace(content=[
        SimpleNamespace(type="text", text="hello "),
        SimpleNamespace(type="tool_use", input={}),
        SimpleNamespace(type="text", text="world"),
    ])
    assert _extract_text(resp) == "hello world"


def test_extract_text_handles_missing_content():
    assert _extract_text(SimpleNamespace()) == ""
    assert _extract_text(SimpleNamespace(content=None)) == ""
