import json
import re
import subprocess
import sys

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OpenJury" in result.stdout
    assert "batch-eval" in result.stdout


def test_cli_batch_eval_help_includes_summary_output():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "batch-eval", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "--summary-output" in _strip_ansi(result.stdout)


def test_cli_list_jurors_shows_criteria():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "list-jurors"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "factuality" in result.stdout
    assert "majority" not in result.stdout


def test_cli_list_jurors_with_config(tmp_path):
    config_data = {
        "name": "Test Jury",
        "score_scale": 5,
        "llm_provider": {
            "provider": "openai_compatible",
            "model_name": "openai/gpt-4o-mini",
            "api_key": "test-api-key",
        },
        "criteria": [
            {
                "name": "helpfulness",
                "description": "Is the response helpful?",
                "weight": 1.0,
            }
        ],
        "jurors": [{"name": "Test Juror", "weight": 1.0}],
    }

    config_file = tmp_path / "test_config.json"
    with open(config_file, "w") as f:
        json.dump(config_data, f)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "openjury.cli",
            "list-jurors",
            "--config",
            str(config_file),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Test Juror" in result.stdout


def test_cli_export_results(tmp_path):
    results_data = [
        {
            "case_id": "c1",
            "run_metadata": {"jury_name": "My Jury"},
            "eval": {
                "composite_score": 4.2,
                "normalized_composite_score": 0.84,
                "score_scale": 5,
            },
            "error": None,
        }
    ]

    results_file = tmp_path / "results.jsonl"
    results_file.write_text(
        "\n".join(json.dumps(r) for r in results_data), encoding="utf-8"
    )
    output_file = tmp_path / "output.csv"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "openjury.cli",
            "export-results",
            "--input",
            str(results_file),
            "--output",
            str(output_file),
            "--format",
            "csv",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert output_file.exists()
    content = output_file.read_text()
    assert "composite_score" in content


def test_cli_list_configs():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "list-configs"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Example configuration structure" in result.stdout
    assert "score_scale" in result.stdout
