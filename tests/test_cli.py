import json
import subprocess
import sys


def test_cli_help():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "OpenJury" in result.stdout


def test_cli_list_jurors():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "list-jurors"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "factuality" in result.stdout
    assert "majority" in result.stdout


def test_cli_list_jurors_with_config(tmp_path):
    config_data = {
        "name": "Test Jury",
        "criteria": [
            {"name": "factuality", "description": "Test criterion", "weight": 1.0, "max_score": 5}
        ],
        "jurors": [
            {
                "name": "Test Juror",
                "model_name": "openai/gpt-4o-mini",
                "weight": 1.0
            }
        ],
        "voting_method": "weighted"
    }

    config_file = tmp_path / "test_config.json"
    with open(config_file, "w") as f:
        json.dump(config_data, f)

    result = subprocess.run(
        [
            sys.executable, "-m", "openjury.cli", "list-jurors",
            "--config", str(config_file)
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Test Juror" in result.stdout


def test_cli_export_results(tmp_path):
    results_data = {
        "winner": "response_1",
        "confidence": 0.8,
        "scores": {
            "response_1": 4.5,
            "response_2": 3.2
        }
    }

    results_file = tmp_path / "results.json"
    with open(results_file, "w") as f:
        json.dump(results_data, f)

    output_file = tmp_path / "output.csv"

    result = subprocess.run(
        [
            sys.executable, "-m", "openjury.cli", "export-results",
            "--input", str(results_file),
            "--output", str(output_file),
            "--format", "csv"
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert output_file.exists()


def test_cli_list_configs():
    result = subprocess.run(
        [sys.executable, "-m", "openjury.cli", "list-configs"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Example configuration structure" in result.stdout 