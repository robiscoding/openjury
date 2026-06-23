import json
import re
from typing import Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from openjury.config import AgentResponse, CriterionConfig, JurorConfig
from openjury.env import get_env_vars
from openjury.logger import logger
from openjury.prompt_templates import PromptTemplate
from openjury.scoring import JurorScore


class JurorException(Exception):
    pass


class Juror:
    def __init__(self, config: JurorConfig):
        self.config = config
        self.name = config.name

        env_vars = get_env_vars()

        self.llm = ChatOpenAI(
            model_name=config.model_name,
            temperature=config.temperature,
            openai_api_key=env_vars["api_key"],
            base_url=env_vars["base_url"],
            max_retries=3,
        )

        self.system_prompt = PromptTemplate.create_system_prompt(config.system_prompt)

    def __repr__(self) -> str:
        return (
            f"Juror(name='{self.name}', model='{self.config.model_name}', "
            f"weight={self.config.weight})"
        )

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
        scores: Dict[str, float] = {}
        explanations: Dict[str, str] = {}
        numbers = re.findall(r"\b([1-9]|10)\b", response_text)

        for i, criterion in enumerate(criteria):
            if i < len(numbers):
                scores[criterion.name] = float(numbers[i])
                explanations[criterion.name] = "Parsed from fallback method"
            else:
                scores[criterion.name] = 3.0
                explanations[criterion.name] = "Default score — could not parse"

        return scores, explanations

    def evaluate(
        self,
        prompt: str,
        response: AgentResponse,
        criteria: List[CriterionConfig],
        score_scale: int = 5,
        max_retries: int = 1,
        evaluation_template: Optional[str] = None,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
    ) -> JurorScore:
        if not criteria:
            raise JurorException("No criteria provided for evaluation")

        evaluation_prompt = PromptTemplate.create_evaluation_prompt(
            prompt=prompt,
            response=response,
            criteria=criteria,
            custom_template=evaluation_template,
            score_scale=score_scale,
            references=references,
            case_rules=case_rules,
        )

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=evaluation_prompt),
        ]

        last_error: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"Juror {self.name} evaluation attempt {attempt + 1}")
                llm_response = self.llm.invoke(messages)
                response_text = llm_response.content
                logger.info(f"Juror {self.name} raw response: {response_text[:300]}")

                scores, explanations = self._parse_evaluation_response(
                    response_text, criteria
                )

                expected_criteria = {c.name for c in criteria}
                missing = expected_criteria - scores.keys()
                if missing:
                    raise JurorException(
                        f"Juror {self.name} missing scores for criteria: {missing}"
                    )

                logger.debug(f"Juror {self.name} evaluation successful: {scores}")
                return JurorScore(
                    juror_name=self.name,
                    juror_weight=self.config.weight,
                    criterion_scores=scores,
                    criterion_explanations=explanations,
                )

            except Exception as e:
                last_error = e
                logger.warning(f"Juror {self.name} attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error(
                        f"Juror {self.name} failed after {max_retries} attempts"
                    )

        raise JurorException(
            f"Juror {self.name} failed after {max_retries} attempts. "
            f"Last error: {last_error}"
        )
