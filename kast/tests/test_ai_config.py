"""Tests for kast.ai.config — env-var > yaml > error precedence."""

import pytest

from kast.ai import AIConfigError
from kast.ai import config as config_mod


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """Strip AI env vars and point CONFIG_PATH at a tmp file."""
    for var in ("KAST_AI_API_KEY", "KAST_AI_PROVIDER", "KAST_AI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    fake_config = tmp_path / "ai.yaml"
    monkeypatch.setattr(config_mod, "CONFIG_PATH", fake_config)
    return fake_config


def test_no_key_anywhere_raises(isolated_env):
    with pytest.raises(AIConfigError, match="No AI API key"):
        config_mod.get_ai_adapter()


def test_env_var_provides_key(isolated_env, monkeypatch):
    monkeypatch.setenv("KAST_AI_API_KEY", "sk-from-env")
    adapter = config_mod.get_ai_adapter()
    # We don't make API calls; just verify the adapter was constructed.
    assert adapter.model == "claude-sonnet-4-6"


def test_yaml_config_provides_key(isolated_env):
    isolated_env.write_text(
        "provider: anthropic\napi_key: sk-from-yaml\nmodel: my-model\n"
    )
    adapter = config_mod.get_ai_adapter()
    assert adapter.model == "my-model"


def test_env_var_overrides_yaml_key(isolated_env, monkeypatch):
    isolated_env.write_text(
        "provider: anthropic\napi_key: sk-from-yaml\nmodel: yaml-model\n"
    )
    monkeypatch.setenv("KAST_AI_API_KEY", "sk-from-env")
    adapter = config_mod.get_ai_adapter()
    # Env wins for the key. Model still resolves from yaml since no env override.
    assert adapter.model == "yaml-model"


def test_model_override_arg_wins(isolated_env, monkeypatch):
    monkeypatch.setenv("KAST_AI_API_KEY", "sk-test")
    monkeypatch.setenv("KAST_AI_MODEL", "env-model")
    isolated_env.write_text("provider: anthropic\napi_key: x\nmodel: yaml-model\n")
    adapter = config_mod.get_ai_adapter(model_override="explicit-model")
    assert adapter.model == "explicit-model"


def test_unknown_provider_raises(isolated_env, monkeypatch):
    monkeypatch.setenv("KAST_AI_API_KEY", "sk-test")
    monkeypatch.setenv("KAST_AI_PROVIDER", "totally-fake")
    with pytest.raises(AIConfigError, match="Unknown AI provider"):
        config_mod.get_ai_adapter()


def test_malformed_yaml_raises(isolated_env):
    isolated_env.write_text("provider: anthropic\n  bad: indent: here\n")
    with pytest.raises(AIConfigError, match="Failed to parse"):
        config_mod.get_ai_adapter()
