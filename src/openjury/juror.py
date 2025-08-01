import json
import re
from typing import Dict, List

from langchain.schema import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from openjury.config import CriterionConfig, JurorConfig, ResponseCandidate
from openjury.env import get_env_vars
from openjury.logger import logger
from openjury.prompt_templates import PromptTemplate


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
        return f"Juror(name='{self.name}', model='{self.config.model_name}', weight={self.config.weight})"

    def _parse_evaluation_response(
        self,
        response_text: str,
        responses: List[ResponseCandidate],
        criteria: List[CriterionConfig],
    ) -> tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, str]]]:

        try:
            json_match = re.search(
                r"```json\s*(\{.*?\})\s*```", response_text, re.DOTALL
            )
            if json_match:
                json_text = json_match.group(1)
            else:
                json_text = response_text.strip()

            evaluation_data = json.loads(json_text)
            scores = {}
            explanations = {}
            evaluations = evaluation_data.get("evaluations", [])
            criterion_names = {criterion.name.name for criterion in criteria}

            for eval_item in evaluations:
                response_id = eval_item.get("response_id", "")

                scores[response_id] = {}
                explanations[response_id] = {}

                eval_scores = eval_item.get("scores", {})
                for criterion_name, score_data in eval_scores.items():
                    normalized_criterion_name = (
                        criterion_name.split(".")[-1]
                        if "." in criterion_name
                        else criterion_name
                    )
                    if normalized_criterion_name in criterion_names:
                        if isinstance(score_data, dict):
                            score = score_data.get("score", 0)
                            explanation = score_data.get("explanation", "")
                        else:
                            score = float(score_data)
                            explanation = eval_item.get("overall_comment", "")
                        scores[response_id][normalized_criterion_name] = float(score)
                        explanations[response_id][normalized_criterion_name] = str(
                            explanation
                        )
            return scores, explanations
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(f"Failed to parse juror response: {e}")
            logger.warning(f"Response text: {response_text}")
            return self._fallback_parse(response_text, responses, criteria)

    def _fallback_parse(
        self,
        response_text: str,
        responses: List[ResponseCandidate],
        criteria: List[CriterionConfig],
    ) -> tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, str]]]:
        scores = {}
        explanations = {}
        numbers = re.findall(r"\b([1-5])\b", response_text)
        num_responses = len(responses)
        num_criteria = len(criteria)
        expected_scores = num_responses * num_criteria

        if len(numbers) >= expected_scores:
            score_idx = 0
            for i in range(num_responses):
                response_key = responses[i].id
                scores[response_key] = {}
                explanations[response_key] = {}
                for criterion in criteria:
                    if score_idx < len(numbers):
                        scores[response_key][criterion.name.name] = float(
                            numbers[score_idx]
                        )
                        explanations[response_key][
                            criterion.name.name
                        ] = "Parsed from fallback method"
                        score_idx += 1
                    else:
                        scores[response_key][criterion.name.name] = 3.0
                        explanations[response_key][
                            criterion.name.name
                        ] = "Default score"
        else:
            for i in range(num_responses):
                response_key = responses[i].id
                scores[response_key] = {}
                explanations[response_key] = {}
                for criterion in criteria:
                    scores[response_key][criterion.name.name] = 3.0
                    explanations[response_key][
                        criterion.name.name
                    ] = "Could not parse score from response"
        return scores, explanations

    def evaluate(
        self,
        prompt: str,
        responses: List[ResponseCandidate],
        criteria: List[CriterionConfig],
        max_retries: int = 1,
    ) -> tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, str]]]:
        if not responses:
            raise JurorException("No responses provided for evaluation")

        if not criteria:
            raise JurorException("No criteria provided for evaluation")

        last_error = None
        evaluation_prompt = PromptTemplate.create_evaluation_prompt(
            prompt=prompt,
            responses=responses,
            criteria=criteria,
            max_score=max(criterion.max_score for criterion in criteria),
        )

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=evaluation_prompt),
        ]

        for attempt in range(max_retries):
            try:
                logger.debug(f"Juror {self.name} evaluation attempt {attempt + 1}")
                response = self.llm.invoke(messages)
                response_text = response.content
                logger.info(f"Juror {self.name} response: {response_text}")
                scores, explanations = self._parse_evaluation_response(
                    response_text, responses, criteria
                )
                logger.info(f"Juror {self.name} scores: {scores}")
                logger.info(f"Juror {self.name} explanations: {explanations}")

                expected_responses = {response.id for response in responses}
                expected_criteria = {criterion.name.name for criterion in criteria}

                for response_key in expected_responses:
                    if response_key not in scores:
                        raise JurorException(f"Missing scores for {response_key}")
                    for criterion_name in expected_criteria:
                        if criterion_name not in scores[response_key]:
                            raise JurorException(
                                f"Missing score for {response_key}, criterion {criterion_name}"
                            )
                logger.debug(f"Juror {self.name} evaluation successful")
                return scores, explanations

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Juror {self.name} evaluation attempt {attempt + 1} failed: {e}"
                )
                if attempt == max_retries - 1:
                    logger.error(
                        f"Juror {self.name} failed after {max_retries} attempts"
                    )
        raise JurorException(
            f"Juror {self.name} failed to evaluate after {max_retries} attempts. Last error: {last_error}"
        )
