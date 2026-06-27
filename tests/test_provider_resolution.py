"""Tests for llm_provider resolution and provider dispatch."""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from openjury.config import (
    JurorConfig,
    JurorProvider,
    JuryConfig,
    LLMProviderConfig,
    resolve_juror_llm_config,
)
from openjury.env import ConfigurationError, expand_env_vars
from openjury.juror import Juror


class TestExpandEnvVars:
    def test_no_placeholder_unchanged(self):
        assert expand_env_vars("plain-key-123") == "plain-key-123"

    def test_single_placeholder(self, monkeypatch):
        monkeypatch.setenv("MY_KEY", "secret")
        assert expand_env_vars("${MY_KEY}") == "secret"

    def test_placeholder_in_url(self, monkeypatch):
        monkeypatch.setenv("BASE", "https://api.example.com/v1")
        assert expand_env_vars("${BASE}") == "https://api.example.com/v1"

    def test_missing_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ConfigurationError, match="MISSING_VAR"):
            expand_env_vars("${MISSING_VAR}")


class TestResolveJurorLLMConfig:
    def _global_provider(self, **kwargs):
        defaults = {
            "provider": JurorProvider.OPENAI_COMPATIBLE,
            "model_name": "gpt-4o-mini",
            "api_key": "global-key",
            "base_url": "https://global.example.com/v1",
        }
        defaults.update(kwargs)
        return LLMProviderConfig(**defaults)

    def test_uses_global_llm_provider_when_juror_has_no_override(self):
        juror = JurorConfig(name="j1")
        resolved = resolve_juror_llm_config(juror, self._global_provider())
        assert resolved.model_name == "gpt-4o-mini"
        assert resolved.api_key == "global-key"
        assert resolved.base_url == "https://global.example.com/v1"

    def test_full_juror_override_replaces_global_bundle(self):
        juror = JurorConfig(
            name="claude",
            model_name="claude-opus-4-5",
            provider=JurorProvider.ANTHROPIC,
            api_key="ant-key",
        )
        resolved = resolve_juror_llm_config(juror, self._global_provider())
        assert resolved.provider == JurorProvider.ANTHROPIC
        assert resolved.model_name == "claude-opus-4-5"
        assert resolved.api_key == "ant-key"
        assert resolved.base_url is None

    def test_override_uses_juror_base_url_not_global(self):
        juror = JurorConfig(
            name="xai",
            model_name="grok-3",
            provider=JurorProvider.OPENAI_COMPATIBLE,
            api_key="xai-key",
            base_url="https://api.x.ai/v1",
        )
        resolved = resolve_juror_llm_config(juror, self._global_provider())
        assert resolved.base_url == "https://api.x.ai/v1"

    def test_missing_global_and_juror_override_raises(self):
        juror = JurorConfig(name="j1")
        with pytest.raises(ConfigurationError, match="llm_provider"):
            resolve_juror_llm_config(juror, None)

    def test_partial_override_only_api_key_invalid_at_validation(self):
        with pytest.raises(ValidationError, match="model_name, api_key, and provider"):
            JurorConfig(name="j1", api_key="only-key")

    def test_partial_override_only_model_name_invalid_at_validation(self):
        with pytest.raises(ValidationError, match="model_name, api_key, and provider"):
            JurorConfig(name="j1", model_name="gpt-4o")


@patch("openjury.juror.OpenAI")
class TestOpenAICompatibleJuror:
    def _global_provider(self):
        return LLMProviderConfig(
            provider=JurorProvider.OPENAI_COMPATIBLE,
            model_name="gpt-4o",
            api_key="global-key",
        )

    def test_uses_global_llm_provider(self, mock_openai_class):
        mock_openai_class.return_value = MagicMock()
        juror = Juror(JurorConfig(name="j"), jury_llm_provider=self._global_provider())
        call_kwargs = mock_openai_class.call_args.kwargs
        assert call_kwargs["api_key"] == "global-key"
        assert juror.llm_config.model_name == "gpt-4o"

    def test_full_juror_override(self, mock_openai_class):
        mock_openai_class.return_value = MagicMock()
        cfg = JurorConfig(
            name="xai",
            model_name="grok-3",
            provider=JurorProvider.OPENAI_COMPATIBLE,
            api_key="xai-key",
            base_url="https://api.x.ai/v1",
        )
        juror = Juror(cfg, jury_llm_provider=self._global_provider())
        call_kwargs = mock_openai_class.call_args.kwargs
        assert call_kwargs["api_key"] == "xai-key"
        assert call_kwargs["base_url"] == "https://api.x.ai/v1"
        assert juror.llm_config.model_name == "grok-3"

    def test_env_var_interpolation_on_resolved_credentials(
        self, mock_openai_class, monkeypatch
    ):
        mock_openai_class.return_value = MagicMock()
        monkeypatch.setenv("TEST_API_KEY", "resolved-key")
        provider = LLMProviderConfig(
            provider=JurorProvider.OPENAI_COMPATIBLE,
            model_name="gpt-4o",
            api_key="${TEST_API_KEY}",
        )
        Juror(JurorConfig(name="j"), jury_llm_provider=provider)
        assert mock_openai_class.call_args.kwargs["api_key"] == "resolved-key"

    def test_missing_llm_provider_raises_configuration_error(self, mock_openai_class):
        with pytest.raises(ConfigurationError):
            Juror(JurorConfig(name="j"))


class TestAnthropicJuror:
    def test_anthropic_provider_uses_anthropic_client(self):
        cfg = JurorConfig(
            name="claude",
            model_name="claude-opus-4-5",
            provider=JurorProvider.ANTHROPIC,
            api_key="ant-key",
        )

        mock_anthropic_module = MagicMock()
        mock_anthropic_module.Anthropic.return_value = MagicMock()

        with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
            Juror(cfg)
            mock_anthropic_module.Anthropic.assert_called_once()
            call_kwargs = mock_anthropic_module.Anthropic.call_args.kwargs
            assert call_kwargs["api_key"] == "ant-key"

    def test_anthropic_missing_package_raises_import_error(self):
        cfg = JurorConfig(
            name="claude",
            model_name="claude-opus-4-5",
            provider=JurorProvider.ANTHROPIC,
            api_key="ant-key",
        )

        with patch.dict("sys.modules", {"anthropic": None}):
            with pytest.raises(ImportError, match="openjury\\[anthropic\\]"):
                Juror(cfg)


@patch("openjury.jury_engine.Juror")
class TestJuryLevelCredentialPassthrough:
    def test_jury_llm_provider_passed_to_juror(self, mock_juror_class):
        from openjury.jury_engine import OpenJury

        mock_juror_class.return_value = MagicMock(name="J")
        llm_provider = LLMProviderConfig(
            provider=JurorProvider.OPENAI_COMPATIBLE,
            model_name="gpt-4o",
            api_key="shared-key",
        )

        config = JuryConfig(
            name="Test",
            llm_provider=llm_provider,
            criteria=[],
            jurors=[JurorConfig(name="J1")],
        )

        OpenJury(config)

        _, call_kwargs = mock_juror_class.call_args
        assert call_kwargs["jury_llm_provider"] == llm_provider
