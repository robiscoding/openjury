import json
import random
import re
import time
from typing import Any, Dict, List, Optional

from openai import OpenAI

from openjury.config import (
    AgentResponse,
    CriterionConfig,
    JurorConfig,
    JurorProvider,
    LLMProviderConfig,
    resolve_juror_llm_config,
)
from openjury.env import expand_env_vars
from openjury.errors import JurorErrorCode, JurorException
from openjury.logger import logger
from openjury.prompt_templates import PromptTemplate
from openjury.scoring import JurorScore

__all__ = ["Juror", "JurorException"]

_TRANSIENT_HTTP_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


def _expand_llm_credentials(llm_config: LLMProviderConfig) -> tuple[str, Optional[str]]:
    api_key = expand_env_vars(llm_config.api_key)
    base_url = expand_env_vars(llm_config.base_url) if llm_config.base_url else None
    return api_key, base_url


def _build_openai_client(api_key: str, base_url: Optional[str]) -> OpenAI:
    return OpenAI(api_key=api_key, base_url=base_url, max_retries=0)


def _build_anthropic_client(api_key: str) -> Any:
    try:
        import anthropic
    except ImportError as exc:
        raise ImportError(
            "anthropic is required for Anthropic jurors. "
            "Install it with: pip install openjury[anthropic]"
        ) from exc
    return anthropic.Anthropic(api_key=api_key)


def _retry_backoff_seconds(attempt: int) -> float:
    base = 0.5 * (2**attempt)
    return min(30.0, base) + random.uniform(0.0, 0.25)


def _is_transient_provider_error(exc: Exception) -> bool:
    if isinstance(exc, JurorException):
        return False

    try:
        import httpx

        if isinstance(
            exc, (httpx.TimeoutException, httpx.NetworkError, httpx.ConnectError)
        ):
            return True
    except ImportError:
        pass

    try:
        from openai import APITimeoutError, RateLimitError

        if isinstance(exc, (APITimeoutError, RateLimitError)):
            return True
    except ImportError:
        pass

    status_code = getattr(exc, "status_code", None)
    if status_code in _TRANSIENT_HTTP_STATUS_CODES:
        return True

    response = getattr(exc, "response", None)
    if response is not None:
        response_status = getattr(response, "status_code", None)
        if response_status in _TRANSIENT_HTTP_STATUS_CODES:
            return True

    message = str(exc).lower()
    transient_markers = (
        "429",
        "503",
        "502",
        "504",
        "408",
        "rate limit",
        "timeout",
        "timed out",
        "overloaded",
        "connection reset",
        "connection error",
    )
    return any(marker in message for marker in transient_markers)


class Juror:
    def __init__(
        self,
        config: JurorConfig,
        jury_llm_provider: Optional[LLMProviderConfig] = None,
    ):
        self.config = config
        self.name = config.name

        llm_config = resolve_juror_llm_config(config, jury_llm_provider)
        self.llm_config = llm_config
        api_key, base_url = _expand_llm_credentials(llm_config)

        if llm_config.provider == JurorProvider.ANTHROPIC:
            self._llm_client: Any = _build_anthropic_client(api_key)
        else:
            self._llm_client = _build_openai_client(api_key, base_url)

        self.system_prompt = PromptTemplate.create_system_prompt(config.system_prompt)

    def __repr__(self) -> str:
        return (
            f"Juror(name='{self.name}', model='{self.llm_config.model_name}', "
            f"weight={self.config.weight})"
        )

    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """Dispatch a single LLM call and return the raw text response."""
        if self.llm_config.provider == JurorProvider.ANTHROPIC:
            response = self._llm_client.messages.create(
                model=self.llm_config.model_name,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=self.config.temperature,
            )
            return response.content[0].text
        else:
            response = self._llm_client.chat.completions.create(
                model=self.llm_config.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.config.temperature,
            )
            return response.choices[0].message.content or ""

    def _parse_evaluation_response(
        self,
        response_text: str,
        criteria: List[CriterionConfig],
    ) -> tuple[Dict[str, float], Dict[str, str]]:
        """Parse juror LLM output into criterion scores and explanations.

        Expected JSON shape:
        {
          "scores": {
            "criterion_name": {"score": N, "explanation": "..."}
          },
          "overall_comment": "..."
        }
        """
        criterion_names = {c.name for c in criteria}

        try:
            json_match = re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            json_text = json_match.group(1) if json_match else response_text.strip()

            data = json.loads(json_text)
            scores: Dict[str, float] = {}
            explanations: Dict[str, str] = {}

            raw_scores = data.get("scores", {})
            for criterion_name, score_data in raw_scores.items():
                normalized = criterion_name.split(".")[-1].lower()
                matched: Optional[str] = None
                for cname in criterion_names:
                    if cname.lower() == normalized:
                        matched = cname
                        break

                if matched is None:
                    continue

                if isinstance(score_data, dict):
                    score = float(score_data.get("score", 0))
                    explanation = str(score_data.get("explanation", ""))
                else:
                    score = float(score_data)
                    explanation = str(data.get("overall_comment", ""))

                scores[matched] = score
                explanations[matched] = explanation

            return scores, explanations

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse juror response: {e}")
            logger.warning(f"Response text: {response_text[:500]}")
            return self._fallback_parse(response_text, criteria)

    def _fallback_parse(
        self,
        response_text: str,
        criteria: List[CriterionConfig],
    ) -> tuple[Dict[str, float], Dict[str, str]]:
        raise JurorException(
            f"Juror '{self.name}' could not parse a valid JSON evaluation from the "
            f"LLM response. Response snippet: {response_text[:200]!r}",
            code=JurorErrorCode.JUROR_PARSE_ERROR,
        )

    def evaluate(
        self,
        prompt: str,
        response: AgentResponse,
        criteria: List[CriterionConfig],
        score_min: int = 1,
        score_scale: int = 5,
        max_retries: int = 1,
        evaluation_template: Optional[str] = None,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
    ) -> JurorScore:
        if not criteria:
            raise JurorException(
                "No criteria provided for evaluation",
                code=JurorErrorCode.JUROR_ERROR,
            )

        evaluation_prompt = PromptTemplate.create_evaluation_prompt(
            prompt=prompt,
            response=response,
            criteria=criteria,
            custom_template=evaluation_template,
            score_min=score_min,
            score_scale=score_scale,
            references=references,
            case_rules=case_rules,
        )

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"Juror {self.name} evaluation attempt {attempt + 1}")
                started = time.perf_counter()
                response_text = self._call_llm(self.system_prompt, evaluation_prompt)
                latency_ms = int((time.perf_counter() - started) * 1000)
                logger.info(f"Juror {self.name} raw response: {response_text[:300]}")

                scores, explanations = self._parse_evaluation_response(
                    response_text, criteria
                )

                expected_criteria = {c.name for c in criteria}
                missing = expected_criteria - scores.keys()
                if missing:
                    raise JurorException(
                        f"Juror {self.name} missing scores for criteria: {missing}",
                        code=JurorErrorCode.JUROR_MISSING_CRITERIA,
                    )
                invalid_scores = {
                    name: score
                    for name, score in scores.items()
                    if not score.is_integer() or not score_min <= score <= score_scale
                }
                if invalid_scores:
                    raise JurorException(
                        f"Juror {self.name} returned scores outside the integer "
                        f"range {score_min}-{score_scale}: {invalid_scores}",
                        code=JurorErrorCode.JUROR_PARSE_ERROR,
                    )

                logger.debug(f"Juror {self.name} evaluation successful: {scores}")
                return JurorScore(
                    juror_name=self.name,
                    juror_weight=self.config.weight,
                    criterion_scores=scores,
                    criterion_explanations=explanations,
                    latency_ms=latency_ms,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"Juror {self.name} attempt {attempt + 1} failed: {e}")
                is_last_attempt = attempt == max_retries - 1
                if not is_last_attempt and _is_transient_provider_error(e):
                    delay = _retry_backoff_seconds(attempt)
                    logger.info(
                        f"Juror {self.name} retrying in {delay:.2f}s "
                        f"(attempt {attempt + 2}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                if is_last_attempt:
                    logger.error(
                        f"Juror {self.name} failed after {max_retries} attempts"
                    )
                break

        code = JurorErrorCode.JUROR_PROVIDER_ERROR
        if isinstance(last_error, JurorException):
            code = JurorErrorCode(last_error.code)

        raise JurorException(
            f"Juror {self.name} failed after {max_retries} attempts. "
            f"Last error: {last_error}",
            code=code,
        )
