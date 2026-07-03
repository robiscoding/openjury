import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import typer
from rich.console import Console
from rich.table import Table

from openjury.batch_dataset import (
    EndpointSpec,
    assertion_policy_for_case,
    cases_from_config,
    eval_record,
    format_exemplars_for_jury,
    item_eval_to_record,
    load_cases,
    resolve_endpoint,
    serialize_batch_run_summary,
)
from openjury.config import JuryConfig, VotingCriteria
from openjury.endpoint_fetcher import (
    AgentEndpoint,
    EndpointFetchError,
    fetch_all_responses,
    load_endpoints_file,
)
from openjury.execution import EvaluationItem, ExecutionOptions
from openjury.jury_engine import OpenJury
from openjury.output_format import (
    AgentEvalResult,
    ResultFormatter,
    serialize_eval_result,
)

cli_app = typer.Typer(
    name="openjury",
    help="OpenJury — Evaluate agent responses using LLM-based jurors",
    add_completion=False,
)
console = Console()


@cli_app.command()
def run(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to jury configuration JSON file"
    ),
    endpoints_config: Path = typer.Option(
        ...,
        "--endpoints-config",
        "-e",
        help="Path to endpoints JSON file defining which LLM URLs to call.",
    ),
    prompt: Optional[str] = typer.Option(
        None, "--prompt", "-p", help="Single prompt to evaluate."
    ),
    prompts_file: Optional[Path] = typer.Option(
        None,
        "--prompts-file",
        "-P",
        help=(
            "Path to a prompts file (.txt one prompt per line, or .jsonl with "
            '{"prompt": "..."} per line).'
        ),
    ),
    consistency_trials: int = typer.Option(
        0,
        "--consistency-trials",
        help=(
            "Number of extra trials for consistency audit (0 = disabled). "
            "When > 0, the agent is called 1 + N times per prompt; "
            "quality score comes from trial 1, score_std measures reliability."
        ),
    ),
    references: Optional[str] = typer.Option(
        None,
        "--references",
        help="Optional calibration examples text appended to the evaluation prompt",
    ),
    case_rules: Optional[str] = typer.Option(
        None,
        "--case-rules",
        help="Optional per-evaluation rules text appended to the evaluation prompt",
    ),
    output_file: Optional[Path] = typer.Option(
        None, "--output", "-o", help="Output file for results"
    ),
    format: str = typer.Option(
        "text", "--format", "-f", help="Output format (json, text)"
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    try:
        if not config.exists():
            console.print(f"[red]Error: Config file {config} does not exist[/red]")
            raise typer.Exit(1)
        if not endpoints_config.exists():
            console.print(
                f"[red]Error: Endpoints file {endpoints_config} does not exist[/red]"
            )
            raise typer.Exit(1)
        if prompt and prompts_file:
            console.print(
                "[red]Error: --prompt and --prompts-file are mutually exclusive[/red]"
            )
            raise typer.Exit(1)
        if not prompt and not prompts_file:
            console.print("[red]Error: provide either --prompt or --prompts-file[/red]")
            raise typer.Exit(1)

        jury_config = JuryConfig.from_json_file(str(config))

        # --consistency-trials overrides config num_trials when provided
        if consistency_trials > 0:
            jury_config = jury_config.model_copy(
                update={"num_trials": 1 + consistency_trials}
            )

        jury = OpenJury(jury_config)
        endpoints = load_endpoints_file(str(endpoints_config))

        prompts: List[str] = []
        if prompts_file:
            if not prompts_file.exists():
                console.print(
                    f"[red]Error: Prompts file {prompts_file} does not exist[/red]"
                )
                raise typer.Exit(1)
            prompts = _load_prompts_file(prompts_file)
        else:
            prompts = [prompt]  # type: ignore[list-item]

        if verbose:
            console.print(
                f"[green]Running evaluation with {len(jury.jurors)} jurors[/green]"
            )
            console.print(
                f"[green]{len(prompts)} prompt(s) x {len(endpoints)} endpoint(s)[/green]"
            )

        results: List[AgentEvalResult] = []
        for current_prompt in prompts:
            for endpoint in endpoints:
                if verbose:
                    console.print(
                        f"[cyan]Evaluating prompt: {current_prompt[:60]}... "
                        f"endpoint: {endpoint.alias or endpoint.url}[/cyan]"
                    )
                result = jury.evaluate(
                    prompt=current_prompt,
                    endpoint=endpoint,
                    references=references,
                    case_rules=case_rules,
                )
                results.append(result)

        if verbose:
            console.print("[green]Evaluation completed![/green]")

        if format == "json":
            if len(results) == 1:
                output = json.dumps(
                    serialize_eval_result(results[0]), indent=2, ensure_ascii=False
                )
            else:
                output = "\n".join(
                    json.dumps(serialize_eval_result(r), ensure_ascii=False)
                    for r in results
                )
        else:
            output = "\n\n".join(ResultFormatter.format_result(r) for r in results)

        if output_file:
            output_file.write_text(output, encoding="utf-8")
            console.print(f"[green]Results saved to {output_file}[/green]")
        else:
            console.print(output)

    except (EndpointFetchError, Exception) as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@cli_app.command("batch-eval")
def batch_eval(
    config: Path = typer.Option(
        ..., "--config", "-c", help="Path to jury configuration JSON file"
    ),
    input_path: Optional[Path] = typer.Option(
        None,
        "--input",
        "-i",
        help="Dataset path (.jsonl or .csv); omit to use config.dataset",
    ),
    output_path: Path = typer.Option(..., "--output", "-o", help="Output JSONL path"),
    endpoints_config: Optional[Path] = typer.Option(
        None,
        "--endpoints-config",
        "-e",
        help=(
            "Path to endpoints JSON file. Used as a fallback for cases that have "
            "no inline 'endpoints'."
        ),
    ),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-n", help="Maximum number of cases to run"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w", help="Number of concurrent case evaluations"
    ),
    summary_output: Optional[Path] = typer.Option(
        None,
        "--summary-output",
        help="Optional path for batch run summary JSON",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    if not config.exists():
        console.print(f"[red]Error: Config file {config} does not exist[/red]")
        raise typer.Exit(1)
    if input_path is not None and not input_path.exists():
        console.print(f"[red]Error: Dataset {input_path} does not exist[/red]")
        raise typer.Exit(1)

    global_endpoint_specs: Optional[List[EndpointSpec]] = None
    if endpoints_config:
        if not endpoints_config.exists():
            console.print(
                f"[red]Error: Endpoints file {endpoints_config} does not exist[/red]"
            )
            raise typer.Exit(1)
        try:
            raw_endpoints = load_endpoints_file(str(endpoints_config))
            global_endpoint_specs = [
                EndpointSpec.model_validate(ep.model_dump()) for ep in raw_endpoints
            ]
        except Exception as e:
            console.print(f"[red]Error loading endpoints: {e}[/red]")
            raise typer.Exit(1)

    try:
        jury_config = JuryConfig.from_json_file(str(config))
        jury = OpenJury(jury_config)
        cases = (
            load_cases(input_path)
            if input_path is not None
            else cases_from_config(jury_config)
        )
        if not cases:
            raise ValueError(
                "No dataset cases found; provide --input or add config.dataset"
            )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)

    if limit is not None:
        cases = cases[:limit]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_str = str(config.resolve())

    evaluation_items: List[EvaluationItem] = []
    case_ids: List[str] = []
    for case in cases:
        refs, rules = format_exemplars_for_jury(case.exemplars)
        try:
            endpoint = resolve_endpoint(case, global_endpoint_specs)
            assertions, assertion_threshold, quality_threshold = (
                assertion_policy_for_case(case, jury_config)
            )
        except Exception as e:
            console.print(f"[red]Error preparing case {case.case_id}: {e}[/red]")
            raise typer.Exit(1)

        evaluation_items.append(
            EvaluationItem(
                prompt=case.prompt,
                item_id=case.case_id,
                ground_truth=case.ground_truth,
                assertions=assertions,
                assertion_threshold=assertion_threshold,
                quality_threshold=quality_threshold,
                metadata=case.metadata,
                endpoint=endpoint,
                references=refs,
                case_rules=rules,
            )
        )
        case_ids.append(case.case_id)

    batch_result = jury.evaluate_items_with_summary(
        evaluation_items,
        options=ExecutionOptions(
            max_item_workers=max(1, workers),
            ground_truth=None,
        ),
    )

    with output_path.open("w", encoding="utf-8") as out_f:
        for case_id, item_result in zip(case_ids, batch_result.items):
            eval_payload = (
                serialize_eval_result(item_result.result)
                if item_result.result is not None
                else None
            )
            record = item_eval_to_record(
                item_result,
                case_id=case_id,
                config_path=cfg_str,
                jury_name=jury_config.name,
                eval_payload=eval_payload,
            )
            out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
            if verbose:
                status = record.get("status", "scored")
                if status != "scored":
                    console.print(
                        f"[cyan]{case_id}[/cyan] error: {record.get('error')}"
                    )
                else:
                    console.print(f"[cyan]{case_id}[/cyan] ok")

    if summary_output is not None:
        summary_output.parent.mkdir(parents=True, exist_ok=True)
        summary_payload = serialize_batch_run_summary(
            batch_result.summary,
            jury_name=jury_config.name,
            config_path=cfg_str,
            started_at=batch_result.started_at,
            finished_at=batch_result.finished_at,
            duration_ms=batch_result.duration_ms,
            worker_count=max(1, workers),
        )
        summary_output.write_text(
            json.dumps(summary_payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(f"[green]Wrote summary to {summary_output}[/green]")

    console.print(f"[green]Wrote {len(cases)} rows to {output_path}[/green]")


@cli_app.command()
def list_jurors(
    config: Optional[Path] = typer.Option(
        None, "--config", "-c", help="Path to jury configuration JSON file"
    ),
):
    if config:
        if not config.exists():
            console.print(f"[red]Error: Config file {config} does not exist[/red]")
            raise typer.Exit(1)

        try:
            jury_config = JuryConfig.from_json_file(str(config))
            table = Table(title=str(config.resolve()))
            table.add_column("Name", style="cyan")
            table.add_column("Model", style="green")
            table.add_column("Weight", style="yellow")
            table.add_column("Temperature", style="blue")

            global_model = (
                jury_config.llm_provider.model_name if jury_config.llm_provider else "—"
            )
            for juror in jury_config.jurors:
                model = juror.model_name or global_model
                table.add_row(
                    juror.name,
                    model,
                    str(juror.weight),
                    str(juror.temperature),
                )

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            raise typer.Exit(1)
    else:
        console.print("[yellow]Built-in criterion names (VotingCriteria):[/yellow]")
        for c in VotingCriteria:
            console.print(f"  • {c.value}")


@cli_app.command()
def list_configs(
    examples_dir: Optional[Path] = typer.Option(
        None, "--examples-dir", help="Directory containing example configs"
    ),
):
    if examples_dir and examples_dir.exists():
        config_files = list(examples_dir.rglob("*.json"))
        if config_files:
            table = Table(title="Available Configuration Files")
            table.add_column("File", style="cyan")
            table.add_column("Size", style="green")

            for config_file in config_files:
                size = config_file.stat().st_size
                table.add_row(
                    str(config_file.relative_to(examples_dir)), f"{size} bytes"
                )

            console.print(table)
        else:
            console.print("[yellow]No JSON configuration files found[/yellow]")
    else:
        console.print("[yellow]Example configuration structure:[/yellow]")
        example_config = {
            "name": "Example Jury",
            "score_min": 1,
            "score_scale": 5,
            "llm_provider": {
                "provider": "openai_compatible",
                "model_name": "gpt-4o-mini",
                "api_key": "${OPENAI_API_KEY}",
            },
            "criteria": [
                {
                    "name": "factuality",
                    "description": "Is the response factually correct?",
                    "weight": 2.0,
                    "rubric": {
                        "1": "Response contains multiple factual errors",
                        "3": "Response is mostly accurate with minor issues",
                        "5": "Response is completely accurate",
                    },
                },
                {
                    "name": "clarity",
                    "description": "Is the response easy to understand?",
                    "weight": 1.0,
                },
            ],
            "jurors": [
                {
                    "name": "Expert Juror",
                    "weight": 2.0,
                    "temperature": 0.1,
                }
            ],
        }
        console.print(json.dumps(example_config, indent=2))


@cli_app.command()
def export_results(
    results_file: Path = typer.Option(
        ..., "--input", "-i", help="Input results JSONL file"
    ),
    output_file: Path = typer.Option(..., "--output", "-o", help="Output file path"),
    format: str = typer.Option(
        "csv", "--format", "-f", help="Export format (csv, json)"
    ),
    summary_output: Optional[Path] = typer.Option(
        None,
        "--summary-output",
        help="Optional path to write batch summary JSON derived from input rows",
    ),
):
    if not results_file.exists():
        console.print(f"[red]Error: Results file {results_file} does not exist[/red]")
        raise typer.Exit(1)

    try:
        records = []
        with open(results_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        if format == "csv":
            import csv

            with open(output_file, "w", newline="") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(
                    [
                        "case_id",
                        "jury_name",
                        "composite_score",
                        "normalized_score",
                        "assertion_score",
                        "assertions_passed",
                        "passed",
                        "score_scale",
                        "score_std",
                        "num_trials",
                        "error",
                    ]
                )
                for rec in records:
                    ev = rec.get("eval") or {}
                    cr = ev.get("consistency_result") or {}
                    writer.writerow(
                        [
                            rec.get("case_id", ""),
                            rec.get("run_metadata", {}).get("jury_name", ""),
                            ev.get("composite_score", ""),
                            ev.get("normalized_composite_score", ""),
                            ev.get("assertion_score", ""),
                            ev.get("assertions_passed", ""),
                            ev.get("passed", ""),
                            ev.get("score_scale", ""),
                            cr.get("score_std", ""),
                            cr.get("num_trials", ""),
                            rec.get("error", ""),
                        ]
                    )
        elif format == "json":
            with open(output_file, "w") as f:
                json.dump(records, f, indent=2)
        else:
            console.print(f"[red]Error: Unknown format '{format}'[/red]")
            raise typer.Exit(1)

        console.print(f"[green]Results exported to {output_file}[/green]")

        if summary_output is not None:
            from openjury.batch_summary import aggregate_batch_results
            from openjury.execution import (
                EvalItemStatus,
                EvaluationItem,
                ItemEvalResult,
            )

            item_results: List[ItemEvalResult] = []
            for index, rec in enumerate(records):
                status_value = rec.get("status")
                if status_value is None:
                    status = (
                        EvalItemStatus.SCORED
                        if rec.get("error") is None
                        else EvalItemStatus.AGENT_FAILED
                    )
                else:
                    status = EvalItemStatus(status_value)
                item = EvaluationItem(
                    prompt=(rec.get("eval") or {}).get("prompt", ""),
                    item_id=rec.get("case_id"),
                )
                eval_payload = rec.get("eval")
                result = None
                if eval_payload is not None:
                    result = AgentEvalResult.model_validate(eval_payload)
                item_results.append(
                    ItemEvalResult(
                        item=item,
                        index=index,
                        result=result,
                        status=status,
                        error_code=rec.get("error_code"),
                        error_message=rec.get("error"),
                        error_stage=rec.get("error_stage"),
                        evaluation_duration_ms=rec.get("evaluation_duration_ms"),
                    )
                )

            score_scale = 5
            if item_results and item_results[0].result is not None:
                score_scale = item_results[0].result.score_scale
            elif records:
                ev = records[0].get("eval") or {}
                score_scale = ev.get("score_scale", 5)

            summary = aggregate_batch_results(
                item_results,
                score_scale=score_scale,
            )
            run_metadata = records[0].get("run_metadata", {}) if records else {}
            summary_payload = serialize_batch_run_summary(
                summary,
                jury_name=run_metadata.get("jury_name", ""),
                config_path=run_metadata.get("config_path"),
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                duration_ms=0,
                worker_count=1,
            )
            summary_output.parent.mkdir(parents=True, exist_ok=True)
            summary_output.write_text(
                json.dumps(summary_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            console.print(f"[green]Summary exported to {summary_output}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _load_prompts_file(path: Path) -> List[str]:
    suffix = path.suffix.lower()
    prompts: List[str] = []
    if suffix == ".jsonl":
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if "prompt" not in obj:
                        raise ValueError(f"line {lineno}: missing 'prompt' key")
                    prompts.append(obj["prompt"])
                except (json.JSONDecodeError, ValueError) as e:
                    console.print(
                        f"[red]Error in prompts file line {lineno}: {e}[/red]"
                    )
                    raise typer.Exit(1)
    else:
        with path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    prompts.append(line)
    if not prompts:
        console.print(f"[red]Error: Prompts file {path} contains no prompts[/red]")
        raise typer.Exit(1)
    return prompts


app = cli_app

if __name__ == "__main__":
    cli_app()
