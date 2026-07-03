import json
from pathlib import Path

import pytest

from openjury.batch_dataset import (
    BatchCase,
    Exemplars,
    assertion_policy_for_case,
    cases_from_config,
    eval_record,
    format_exemplars_for_jury,
    load_cases,
    resolve_endpoint,
)
from openjury.config import CriterionConfig, JuryConfig
from openjury.prompt_templates import PromptTemplate

ENDPOINT_SPEC = {"url": "http://localhost/ep", "alias": "test-ep"}


def test_load_cases_jsonl(tmp_path: Path):
    p = tmp_path / "d.jsonl"
    row = {
        "case_id": "c1",
        "prompt": "Hi",
        "endpoints": [ENDPOINT_SPEC],
        "exemplars": {
            "adequate": [{"text": "ok", "reason": "fine"}],
            "rules": "Be fair",
        },
        "assertions": [
            {
                "name": "greets",
                "type": "contains",
                "value": "hello",
                "required": True,
                "weight": 2.0,
            }
        ],
        "assertion_threshold": 0.8,
        "quality_threshold": 4.0,
    }
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    cases = load_cases(p)
    assert len(cases) == 1
    assert cases[0].case_id == "c1"
    assert cases[0].exemplars is not None
    assert cases[0].exemplars.rules == "Be fair"
    assert cases[0].endpoints[0].alias == "test-ep"
    assert cases[0].assertions[0].name == "greets"
    assert cases[0].assertion_threshold == 0.8
    assert cases[0].quality_threshold == 4.0


def test_load_cases_csv(tmp_path: Path):
    p = tmp_path / "d.csv"
    ep_json = json.dumps([ENDPOINT_SPEC])
    exemplars_json = json.dumps({"adequate": []})
    ep_csv_cell = '"' + ep_json.replace('"', '""') + '"'
    ex_csv_cell = '"' + exemplars_json.replace('"', '""') + '"'
    p.write_text(
        "case_id,prompt,endpoints_json,exemplars_json\n"
        f"r1,Do math,{ep_csv_cell},{ex_csv_cell}\n",
        encoding="utf-8",
    )
    cases = load_cases(p)
    assert len(cases) == 1
    assert cases[0].case_id == "r1"
    assert cases[0].endpoints[0].url == "http://localhost/ep"


def test_load_cases_csv_with_assertion_policy(tmp_path: Path):
    p = tmp_path / "d.csv"
    ep_json = json.dumps([ENDPOINT_SPEC])
    assertions_json = json.dumps(
        [{"name": "brief", "type": "max_length", "value": 100}]
    )
    ep_csv_cell = '"' + ep_json.replace('"', '""') + '"'
    assertions_csv_cell = '"' + assertions_json.replace('"', '""') + '"'
    p.write_text(
        "case_id,prompt,endpoints_json,assertions_json,"
        "assertion_threshold,quality_threshold\n"
        f"r1,Be brief,{ep_csv_cell},{assertions_csv_cell},0.9,3.5\n",
        encoding="utf-8",
    )

    case = load_cases(p)[0]

    assert case.assertions[0].name == "brief"
    assert case.assertion_threshold == 0.9
    assert case.quality_threshold == 3.5


def test_load_cases_csv_missing_required_column(tmp_path: Path):
    p = tmp_path / "bad.csv"
    p.write_text("case_id,prompt\nr1,test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="endpoints_json"):
        load_cases(p)


def test_batch_case_allows_empty_endpoints_for_global_fallback():
    case = BatchCase(case_id="c1", prompt="p")
    assert case.endpoints == []


def test_resolve_endpoint_selects_first_endpoint():
    case = BatchCase(
        case_id="c1",
        prompt="p",
        endpoints=[
            {"url": "http://localhost/a", "alias": "agent-a"},
            {"url": "http://localhost/b", "alias": "agent-b"},
        ],
    )

    endpoint = resolve_endpoint(case, None)

    assert endpoint.alias == "agent-a"
    assert endpoint.url == "http://localhost/a"


def test_cases_from_inline_config(sample_jury_config):
    data = sample_jury_config.model_dump()
    data["global_assertions"] = [
        {"name": "global", "type": "contains", "value": "summary"}
    ]
    data["assertion_profiles"] = {
        "brief": {
            "checks": [{"name": "brief", "type": "max_length", "value": 100}],
            "assertion_threshold": 1.0,
        }
    }
    data["dataset"] = [
        {
            "id": "inline-1",
            "input": "Summarize this",
            "ground_truth": "A short summary",
            "assertion_profile_ids": ["brief"],
        }
    ]
    config = JuryConfig.model_validate(data)

    case = cases_from_config(config)[0]

    assert case.case_id == "inline-1"
    assert case.prompt == "Summarize this"
    assert case.ground_truth == "A short summary"
    assert case.assertion_profile_ids == ["brief"]
    checks, assertion_threshold, _ = assertion_policy_for_case(case, config)
    assert [check.name for check in checks] == ["global", "brief"]
    assert assertion_threshold == 1.0


def test_external_case_resolves_config_assertion_profile(sample_jury_config):
    data = sample_jury_config.model_dump()
    data["assertion_profiles"] = {
        "cited": {
            "checks": [{"name": "citation", "type": "contains", "value": "https://"}],
            "quality_threshold": 4.0,
        }
    }
    config = JuryConfig.model_validate(data)
    case = BatchCase(
        case_id="external-1", prompt="Research", assertion_profile_ids=["cited"]
    )

    checks, assertion_threshold, quality_threshold = assertion_policy_for_case(
        case, config
    )

    assert checks[0].name == "citation"
    assert assertion_threshold is None
    assert quality_threshold == 4.0


def test_case_combines_multiple_assertion_profiles_without_thresholds(
    sample_jury_config,
):
    data = sample_jury_config.model_dump()
    data["assertion_profiles"] = {
        "cited": {
            "checks": [{"name": "citation", "type": "contains", "value": "https://"}],
        },
        "brief": {
            "checks": [{"name": "brief", "type": "max_length", "value": 500}],
        },
    }
    config = JuryConfig.model_validate(data)
    case = BatchCase(
        case_id="external-1",
        prompt="Research",
        assertion_profile_ids=["cited", "brief"],
    )

    checks, assertion_threshold, quality_threshold = assertion_policy_for_case(
        case, config
    )

    assert [check.name for check in checks] == ["citation", "brief"]
    assert assertion_threshold is None
    assert quality_threshold is None


def test_case_rejects_multiple_profiles_with_thresholds(sample_jury_config):
    data = sample_jury_config.model_dump()
    data["assertion_profiles"] = {
        "cited": {
            "checks": [{"name": "citation", "type": "contains", "value": "https://"}],
            "assertion_threshold": 0.8,
        },
        "brief": {
            "checks": [{"name": "brief", "type": "max_length", "value": 500}],
            "quality_threshold": 4.0,
        },
    }
    config = JuryConfig.model_validate(data)
    case = BatchCase(
        case_id="external-1",
        prompt="Research",
        assertion_profile_ids=["cited", "brief"],
    )

    with pytest.raises(ValueError, match="define thresholds"):
        assertion_policy_for_case(case, config)


def test_format_exemplars_for_jury_splits_rules():
    refs, rules = format_exemplars_for_jury(
        Exemplars(
            adequate=[{"text": "A", "reason": "good"}],
            inadequate=[{"text": "B", "reason": "bad"}],
            rules="Extra",
        )
    )
    assert (
        refs is not None and "Adequate example" in refs and "Inadequate example" in refs
    )
    assert rules == "Extra"


def test_eval_record_shape():
    record = eval_record(
        case_id="c1",
        config_path="/path/to/config.json",
        jury_name="My Jury",
        eval_payload={"composite_score": 4.2},
        error=None,
    )
    assert record["case_id"] == "c1"
    assert record["eval"]["composite_score"] == 4.2
    assert record["error"] is None
    assert record["run_metadata"]["jury_name"] == "My Jury"


def test_eval_record_with_error():
    record = eval_record(
        case_id="c2",
        config_path=None,
        jury_name="J",
        eval_payload=None,
        error="Fetch failed",
    )
    assert record["error"] == "Fetch failed"
    assert record["eval"] is None


def test_prompt_template_includes_reference_sections():
    from openjury.config import AgentResponse

    criteria = [CriterionConfig(name="factuality", description="d", weight=1.0)]
    response = AgentResponse(content="body", id="r1")
    text = PromptTemplate.create_evaluation_prompt(
        prompt="task",
        response=response,
        criteria=criteria,
        references="Ref body",
        case_rules="Rule body",
    )
    assert "Ref body" in text
    assert "Rule body" in text


def test_prompt_template_includes_rubric():
    from openjury.config import AgentResponse

    criteria = [
        CriterionConfig(
            name="clarity",
            description="Is it clear?",
            weight=1.0,
            rubric={"1": "Confusing", "5": "Crystal clear"},
        )
    ]
    response = AgentResponse(content="Answer", id="r1")
    text = PromptTemplate.create_evaluation_prompt(
        prompt="Q?", response=response, criteria=criteria
    )
    assert "Confusing" in text
    assert "Crystal clear" in text


def test_prompt_template_sorts_rubric_ranges_numerically():
    from openjury.config import AgentResponse

    criterion = CriterionConfig(
        name="clarity",
        description="Is it clear?",
        rubric={"10": "Excellent", "1-2": "Poor", "3-9": "Acceptable"},
    )
    text = PromptTemplate.create_evaluation_prompt(
        prompt="Q?",
        response=AgentResponse(content="Answer", id="r1"),
        criteria=[criterion],
        score_scale=10,
    )
    assert text.index("1-2 — Poor") < text.index("3-9 — Acceptable")
    assert text.index("3-9 — Acceptable") < text.index("10 — Excellent")


def test_prompt_template_supports_zero_based_integer_scores():
    from openjury.config import AgentResponse

    text = PromptTemplate.create_evaluation_prompt(
        prompt="Q?",
        response=AgentResponse(content="Answer", id="r1"),
        criteria=[CriterionConfig(name="clarity", description="Is it clear?")],
        score_min=0,
        score_scale=5,
    )
    assert "score each 0-5" in text
    assert "integer score from 0 to 5" in text
    assert "Rubric ranges are inclusive" in PromptTemplate.DEFAULT_SYSTEM_PROMPT
