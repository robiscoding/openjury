import json
from pathlib import Path

import pytest

from openjury.batch_dataset import (
    BatchCase,
    Exemplars,
    eval_record,
    format_exemplars_for_jury,
    load_cases,
)
from openjury.config import CriterionConfig
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
    }
    p.write_text(json.dumps(row) + "\n", encoding="utf-8")
    cases = load_cases(p)
    assert len(cases) == 1
    assert cases[0].case_id == "c1"
    assert cases[0].exemplars is not None
    assert cases[0].exemplars.rules == "Be fair"
    assert cases[0].endpoints[0].alias == "test-ep"


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


def test_load_cases_csv_missing_required_column(tmp_path: Path):
    p = tmp_path / "bad.csv"
    p.write_text("case_id,prompt\nr1,test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="endpoints_json"):
        load_cases(p)


def test_batch_case_allows_empty_endpoints_for_global_fallback():
    case = BatchCase(case_id="c1", prompt="p")
    assert case.endpoints == []


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
