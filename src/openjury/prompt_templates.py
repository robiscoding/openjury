from typing import List, Optional

from openjury.config import CriterionConfig, ResponseCandidate


class PromptTemplate:

    DEFAULT_SYSTEM_PROMPT = """You are an expert evaluator tasked with judging the quality of responses.
You will evaluate responses based on specific criteria and provide scores with explanations.
Be objective, fair, and consistent in your evaluations."""

    DEFAULT_EVALUATION_TEMPLATE = """Please evaluate the following responses to the given prompt.

**Original Prompt:**
{prompt}

**Responses to Evaluate:**
{responses}

**Evaluation Criteria:**
{criteria}

**Instructions:**
1. Rate each response for each criterion on a scale of 1 to {max_score}
2. Provide a brief explanation for each score
3. Be objective and consider only the quality relative to the criteria
4. Format your response as JSON with the following structure:

```json
{{
  "evaluations": [
    {{
      "response_id": "response_1", 
      "scores": {{
        "{example_criterion_name}": {{
          "score": X,
          "explanation": "Brief explanation for this score"
        }}
      }},
      "overall_comment": "Optional overall comment about this response"
    }}
  ]
}}
```

Please provide your evaluation now."""

    @classmethod
    def format_criteria(cls, criteria: List[CriterionConfig]) -> str:
        criteria_text = []
        for i, criterion in enumerate(criteria, 1):
            criteria_text.append(
                f"{i}. **{criterion.name.name}** (Weight: {criterion.weight}): {criterion.description}"
            )
        return "\n".join(criteria_text)

    @classmethod
    def format_responses(cls, responses: List[ResponseCandidate]) -> str:
        response_text = []
        for i, response in enumerate(responses, 1):
            display_name = response.get_display_name()
            model_info = (
                f" (Model: {response.model_name})" if response.model_name else ""
            )
            response_text.append(
                f"**Response {i} - {display_name}{model_info}:**\n{response.content}\n"
            )
        return "\n".join(response_text)

    @classmethod
    def create_evaluation_prompt(
        cls,
        prompt: str,
        responses: List[ResponseCandidate],
        criteria: List[CriterionConfig],
        custom_template: Optional[str] = None,
        max_score: int = 5,
    ) -> str:
        template = custom_template or cls.DEFAULT_EVALUATION_TEMPLATE
        formatted_criteria = cls.format_criteria(criteria)
        formatted_responses = cls.format_responses(responses)
        example_criterion_name = criteria[0].name.name if criteria else "CRITERION_NAME"

        return template.format(
            prompt=prompt,
            responses=formatted_responses,
            criteria=formatted_criteria,
            max_score=max_score,
            example_criterion_name=example_criterion_name,
        )

    @classmethod
    def create_system_prompt(cls, custom_system_prompt: Optional[str] = None) -> str:
        return custom_system_prompt or cls.DEFAULT_SYSTEM_PROMPT
