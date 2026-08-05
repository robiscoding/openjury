"""Tests for token usage reporting and extra_body pass-through on juror calls."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from openjury import AgentResponse, Juror, JurorConfig, JurorProvider, LLMProviderConfig
from openjury.errors import JurorException
from openjury.scoring import TokenUsage

VALID_SCORES = (
    '{"scores": {"factuality": {"score": 4, "explanation": "ok"}, '
    '"clarity": {"score": 4, "explanation": "ok"}}}'
)

MISSING_CRITERION = '{"scores": {"factuality": {"score": 4, "explanation": "ok"}}}'


def _openai_response(content, usage=None, model=None):
    """An OpenAI-compatible response with real (not auto-mocked) usage fields."""
    choice = MagicMock()
    choice.message.content = content
    return SimpleNamespace(choices=[choice], usage=usage, model=model)


def _anthropic_response(content, usage=None, model=None):
    return SimpleNamespace(
        content=[SimpleNamespace(text=content)], usage=usage, model=model
    )


def _evaluate(juror, criteria, prompt, **kwargs):
    return juror.evaluate(
        prompt=prompt,
        response=AgentResponse(content="answer", id="r1"),
        criteria=criteria,
        **kwargs,
    )


@patch("openjury.juror.OpenAI")
class TestOpenAiUsage:
    def test_usage_surfaced_on_juror_score(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(
            VALID_SCORES,
            usage=SimpleNamespace(
                prompt_tokens=1150,
                completion_tokens=250,
                total_tokens=1400,
                prompt_tokens_details=SimpleNamespace(cached_tokens=128),
                cost=0.00027,
            ),
            model="openai/gpt-oss-20b",
        )
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        score = _evaluate(juror, sample_criteria, sample_prompt)

        assert score.usage == TokenUsage(
            prompt_tokens=1150,
            completion_tokens=250,
            total_tokens=1400,
            cached_tokens=128,
            cost=0.00027,
            model="openai/gpt-oss-20b",
        )

    def test_resolved_model_may_differ_from_requested_model(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        # A router can serve a different model than the one asked for; the
        # served one is what metering has to record.
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(
            VALID_SCORES,
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
            model="deepinfra/actually-served",
        )
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        score = _evaluate(juror, sample_criteria, sample_prompt)

        assert juror.llm_config.model_name == "gpt-3.5-turbo"
        assert score.usage.model == "deepinfra/actually-served"

    def test_usage_is_none_when_provider_reports_none(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(VALID_SCORES)
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        score = _evaluate(juror, sample_criteria, sample_prompt)

        assert score.usage is None

    def test_non_numeric_usage_fields_are_discarded(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        # A response object that answers every attribute (a bare MagicMock, or a
        # gateway echoing junk) must not be read as if it were real metering data.
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(
            VALID_SCORES, usage=MagicMock()
        )
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        score = _evaluate(juror, sample_criteria, sample_prompt)

        assert score.usage is None

    def test_dict_shaped_usage_is_read(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(
            VALID_SCORES,
            usage={
                "prompt_tokens": 900,
                "completion_tokens": 120,
                "prompt_tokens_details": {"cached_tokens": 64},
            },
        )
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        score = _evaluate(juror, sample_criteria, sample_prompt)

        assert score.usage.prompt_tokens == 900
        assert score.usage.completion_tokens == 120
        assert score.usage.cached_tokens == 64
        assert score.usage.total_tokens is None

    def test_unusable_response_still_reports_its_tokens(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        # The call completed and was billed; only its content was unusable.
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(
            MISSING_CRITERION,
            usage=SimpleNamespace(prompt_tokens=1100, completion_tokens=40),
        )
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        with pytest.raises(JurorException) as exc_info:
            _evaluate(juror, sample_criteria, sample_prompt, max_retries=1)

        assert exc_info.value.usage.prompt_tokens == 1100
        assert exc_info.value.usage.completion_tokens == 40

    def test_provider_failure_reports_no_usage(
        self,
        mock_openai_class,
        sample_jurors,
        sample_llm_provider,
        sample_criteria,
        sample_prompt,
    ):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("provider down")
        mock_openai_class.return_value = client

        juror = Juror(sample_jurors[0], jury_llm_provider=sample_llm_provider)
        with pytest.raises(JurorException) as exc_info:
            _evaluate(juror, sample_criteria, sample_prompt, max_retries=1)

        assert exc_info.value.usage is None


class TestAnthropicUsage:
    def _juror(self, mock_module, extra_body=None):
        cfg = JurorConfig(
            name="claude",
            model_name="claude-opus-4-5",
            provider=JurorProvider.ANTHROPIC,
            api_key="ant-key",
            extra_body=extra_body,
        )
        with patch.dict("sys.modules", {"anthropic": mock_module}):
            return Juror(cfg)

    def test_cache_reads_are_counted_separately_from_input(
        self, sample_criteria, sample_prompt
    ):
        client = MagicMock()
        client.messages.create.return_value = _anthropic_response(
            VALID_SCORES,
            usage=SimpleNamespace(
                input_tokens=1000,
                output_tokens=200,
                cache_read_input_tokens=300,
                cache_creation_input_tokens=50,
            ),
            model="claude-opus-4-5",
        )
        module = MagicMock()
        module.Anthropic.return_value = client

        juror = self._juror(module)
        score = _evaluate(juror, sample_criteria, sample_prompt)

        assert score.usage.prompt_tokens == 1000
        assert score.usage.completion_tokens == 200
        assert score.usage.cached_tokens == 300
        # Anthropic reports cache tokens outside input_tokens, so the total is
        # the sum of all four parts rather than input + output.
        assert score.usage.total_tokens == 1550
        assert score.usage.model == "claude-opus-4-5"

    def test_base_url_reaches_the_anthropic_client(self):
        module = MagicMock()
        module.Anthropic.return_value = MagicMock()
        cfg = JurorConfig(
            name="claude",
            model_name="claude-opus-4-5",
            provider=JurorProvider.ANTHROPIC,
            api_key="ant-key",
            base_url="https://gateway.internal/anthropic",
        )

        with patch.dict("sys.modules", {"anthropic": module}):
            Juror(cfg)

        kwargs = module.Anthropic.call_args.kwargs
        assert kwargs["base_url"] == "https://gateway.internal/anthropic"

    def test_base_url_defaults_to_none(self):
        module = MagicMock()
        module.Anthropic.return_value = MagicMock()
        cfg = JurorConfig(
            name="claude",
            model_name="claude-opus-4-5",
            provider=JurorProvider.ANTHROPIC,
            api_key="ant-key",
        )

        with patch.dict("sys.modules", {"anthropic": module}):
            Juror(cfg)

        assert module.Anthropic.call_args.kwargs["base_url"] is None

    def test_extra_body_forwarded(self, sample_criteria, sample_prompt):
        client = MagicMock()
        client.messages.create.return_value = _anthropic_response(VALID_SCORES)
        module = MagicMock()
        module.Anthropic.return_value = client

        juror = self._juror(module, extra_body={"anthropic_beta": ["fine-grained"]})
        _evaluate(juror, sample_criteria, sample_prompt)

        kwargs = client.messages.create.call_args.kwargs
        assert kwargs["extra_body"] == {"anthropic_beta": ["fine-grained"]}


@patch("openjury.juror.OpenAI")
class TestExtraBodyPassThrough:
    def _juror(self, extra_body):
        provider = LLMProviderConfig(
            provider=JurorProvider.OPENAI_COMPATIBLE,
            model_name="openai/gpt-oss-20b",
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            extra_body=extra_body,
        )
        return Juror(JurorConfig(name="j"), jury_llm_provider=provider)

    def test_routing_block_reaches_the_request(
        self, mock_openai_class, sample_criteria, sample_prompt
    ):
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(VALID_SCORES)
        mock_openai_class.return_value = client

        routing = {
            "provider": {
                "sort": "price",
                "allow_fallbacks": True,
                "max_price": {"prompt": 0.20, "completion": 0.60},
                "data_collection": "deny",
            },
            "usage": {"include": True},
        }
        juror = self._juror(routing)
        _evaluate(juror, sample_criteria, sample_prompt)

        kwargs = client.chat.completions.create.call_args.kwargs
        assert kwargs["extra_body"] == routing
        # The fields OpenJury owns are untouched by the pass-through.
        assert kwargs["model"] == "openai/gpt-oss-20b"
        assert len(kwargs["messages"]) == 2

    def test_omitted_when_unset(
        self, mock_openai_class, sample_criteria, sample_prompt
    ):
        client = MagicMock()
        client.chat.completions.create.return_value = _openai_response(VALID_SCORES)
        mock_openai_class.return_value = client

        _evaluate(self._juror(None), sample_criteria, sample_prompt)

        assert "extra_body" not in client.chat.completions.create.call_args.kwargs


class TestTokenUsageMerge:
    def test_merge_sums_present_fields(self):
        merged = TokenUsage(prompt_tokens=100, cost=0.001).merge(
            TokenUsage(prompt_tokens=50, completion_tokens=20, cost=0.002)
        )
        assert merged.prompt_tokens == 150
        assert merged.completion_tokens == 20
        assert merged.cost == pytest.approx(0.003)

    def test_merge_with_none_is_identity(self):
        usage = TokenUsage(prompt_tokens=100)
        assert usage.merge(None) == usage

    def test_merge_prefers_the_later_resolved_model(self):
        merged = TokenUsage(model="a").merge(TokenUsage(model="b"))
        assert merged.model == "b"

        # ...but does not erase a known model with an unknown one.
        assert TokenUsage(model="a").merge(TokenUsage()).model == "a"

    def test_empty_usage_is_detected(self):
        assert TokenUsage().is_empty()
        assert not TokenUsage(prompt_tokens=0).is_empty()
