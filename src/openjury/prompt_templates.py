from typing import List, Optional

from openjury.config import AgentResponse, CriterionConfig


class PromptTemplate:

    DEFAULT_SYSTEM_PROMPT = """You are an expert evaluator tasked with judging the quality of an agent's response.
You will score the response based on specific criteria and provide explanations for each score.
Be objective, fair, and consistent in your evaluations."""

    DEFAULT_EVALUATION_TEMPLATE = """Please evaluate the following agent response to the given prompt.

**Prompt:**
{prompt}

{references_section}{case_rules_section}**Agent Response:**
{response}

**Evaluation Criteria (score each 1-{score_scale}):**
{criteria}

**Instructions:**
1. Rate the response for each criterion on a scale of 1 to {score_scale}
2. Provide a brief explanation for each score
3. Be objective and consider only the quality relative to the criteria
4. Return JSON only — no markdown fences, no extra text:

{{
  "scores": {{
    "{example_criterion_name}": {{
      "score": X,
      "explanation": "Brief explanation for this score"
    }}
  }},
  "overall_comment": "Optional overall comment about this response"
}}"""

    @classmethod
    def auxiliary_sections(
        cls,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
    ) -> tuple[str, str]:
        ref = (references or "").strip()
        rules = (case_rules or "").strip()
        references_section = ""
        if ref:
            references_section = (
                "**Evaluation references (examples for calibration):**\n" f"{ref}\n\n"
            )
        case_rules_section = ""
        if rules:
            case_rules_section = (
                "**Additional rules for this evaluation:**\n" f"{rules}\n\n"
            )
        return references_section, case_rules_section

    @classmethod
    def format_criteria(cls, criteria: List[CriterionConfig]) -> str:
        lines: List[str] = []
        for i, criterion in enumerate(criteria, 1):
            lines.append(
                f"{i}. **{criterion.name}** (weight: {criterion.weight}): "
                f"{criterion.description}"
            )
            if criterion.rubric:
                lines.append("   Score anchors:")
                for level, anchor in sorted(
                    criterion.rubric.items(), key=lambda x: x[0]
                ):
                    lines.append(f"     {level} — {anchor}")
        return "\n".join(lines)

    @classmethod
    def format_response(cls, response: AgentResponse) -> str:
        model_info = f" (Model: {response.model_name})" if response.model_name else ""
        display = response.get_display_name()
        return f"[{display}{model_info}]\n{response.content}"

    @classmethod
    def create_evaluation_prompt(
        cls,
        prompt: str,
        response: AgentResponse,
        criteria: List[CriterionConfig],
        custom_template: Optional[str] = None,
        score_scale: int = 5,
        references: Optional[str] = None,
        case_rules: Optional[str] = None,
    ) -> str:
        template = custom_template or cls.DEFAULT_EVALUATION_TEMPLATE
        formatted_criteria = cls.format_criteria(criteria)
        formatted_response = cls.format_response(response)
        example_criterion_name = criteria[0].name if criteria else "criterion_name"
        references_section, case_rules_section = cls.auxiliary_sections(
            references, case_rules
        )

        return template.format(
            prompt=prompt,
            response=formatted_response,
            criteria=formatted_criteria,
            score_scale=score_scale,
            example_criterion_name=example_criterion_name,
            references_section=references_section,
            case_rules_section=case_rules_section,
        )

    @classmethod
    def create_system_prompt(cls, custom_system_prompt: Optional[str] = None) -> str:
        return custom_system_prompt or cls.DEFAULT_SYSTEM_PROMPT
