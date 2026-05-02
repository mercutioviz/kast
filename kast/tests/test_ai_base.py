"""Tests for kast.ai.base — Protocol satisfaction + dataclass shape."""

from kast.ai import AIAdapter, AIConfigError, AIGenerationError, AIResponse


def test_ai_response_dataclass_fields():
    r = AIResponse(text="hello", tokens_in=5, tokens_out=3, model="m", latency_ms=10)
    assert r.text == "hello"
    assert r.tokens_in == 5
    assert r.tokens_out == 3
    assert r.model == "m"
    assert r.latency_ms == 10
    assert r.raw_response is None


def test_ai_response_with_raw_response():
    raw = {"id": "msg_123"}
    r = AIResponse(text="hi", tokens_in=1, tokens_out=1, model="m",
                   latency_ms=1, raw_response=raw)
    assert r.raw_response == raw


def test_ai_errors_are_runtime_errors():
    assert issubclass(AIConfigError, RuntimeError)
    assert issubclass(AIGenerationError, RuntimeError)


def test_protocol_isinstance_check():
    """Any class with the right ``generate`` signature satisfies AIAdapter."""

    class FakeAdapter:
        def generate(self, *, prompt, system="", response_schema=None,
                     max_tokens=2000, temperature=0.3):
            return AIResponse(text="fake", tokens_in=0, tokens_out=0,
                              model="fake", latency_ms=0)

    fake = FakeAdapter()
    # Protocol satisfaction is structural; this is a smoke check that the
    # call shape works.
    resp = fake.generate(prompt="hi")
    assert resp.text == "fake"
    assert isinstance(fake, AIAdapter)
