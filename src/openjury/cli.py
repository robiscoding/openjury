import json
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from openjury import OpenJury, JuryConfig, ResponseCandidate
from openjury.config import VotingMethod, VotingCriteria
from openjury.output_format import VerdictFormatter

cli_app = typer.Typer(
    name="openjury",
    help="OpenJury - Evaluate and compare multiple model outputs using LLM-based jurors",
    add_completion=False,
)
console = Console()


@cli_app.command()
def run(
    config: Path = typer.Option(..., "--config", "-c", help="Path to jury configuration JSON file"),
    prompt: str = typer.Option(..., "--prompt", "-p", help="The prompt to evaluate"),
    responses: List[str] = typer.Option(..., "--responses", "-r", help="Response texts to evaluate"),
    response_ids: Optional[List[str]] = typer.Option(None, "--response-ids", help="Optional IDs for responses"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file for results"),
    format: str = typer.Option("json", "--format", "-f", help="Output format (json, text, table)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
):
    try:
        if not config.exists():
            console.print(f"[red]Error: Config file {config} does not exist[/red]")
            raise typer.Exit(1)

        jury_config = JuryConfig.from_json_file(str(config))
        jury = OpenJury(jury_config)

        response_candidates = [
            ResponseCandidate(content=response, id=response_ids[i] if response_ids else None)
            for i, response in enumerate(responses)
        ]

        if verbose:
            console.print(f"[green]Running evaluation with {len(jury.jurors)} jurors[/green]")
            console.print(f"[green]Evaluating {len(response_candidates)} responses[/green]")

        verdict = jury.evaluate(prompt=prompt, responses=response_candidates)

        if verbose:
            console.print(f"[green]Evaluation completed![/green]")

        if format == "json":
            result = {
                "winner": verdict.final_verdict.winner,
                "confidence": verdict.final_verdict.confidence,
                "scores": {r: verdict.scores[r] for r in verdict.scores},
                "explanations": verdict.explanations,
                "voting_breakdown": verdict.voting_breakdown,
            }
            output = json.dumps(result, indent=2)
        elif format == "text":
            formatter = VerdictFormatter()
            output = formatter.format_verdict(verdict)
        elif format == "table":
            output = _format_verdict_table(verdict)
        else:
            console.print(f"[red]Error: Unknown format '{format}'[/red]")
            raise typer.Exit(1)

        if output_file:
            output_file.write_text(output)
            console.print(f"[green]Results saved to {output_file}[/green]")
        else:
            console.print(output)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@cli_app.command()
def list_jurors(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Path to jury configuration JSON file"),
):
    if config:
        if not config.exists():
            console.print(f"[red]Error: Config file {config} does not exist[/red]")
            raise typer.Exit(1)

        try:
            jury_config = JuryConfig.from_json_file(str(config))
            table = Table(title=f"Jurors in {config.name}")
            table.add_column("Name", style="cyan")
            table.add_column("Model", style="green")
            table.add_column("Weight", style="yellow")
            table.add_column("Temperature", style="blue")

            for juror in jury_config.jurors:
                table.add_row(
                    juror.name,
                    juror.model_name,
                    str(juror.weight),
                    str(juror.temperature),
                )

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error loading config: {e}[/red]")
            raise typer.Exit(1)
    else:
        console.print("[yellow]Built-in voting criteria:[/yellow]")
        for criteria in VotingCriteria:
            console.print(f"  • {criteria.value}")
        
        console.print("\n[yellow]Built-in voting methods:[/yellow]")
        for method in VotingMethod:
            console.print(f"  • {method.value}")


@cli_app.command()
def list_configs(
    examples_dir: Optional[Path] = typer.Option(None, "--examples-dir", help="Directory containing example configs"),
):
    if examples_dir and examples_dir.exists():
        config_files = list(examples_dir.rglob("*.json"))
        if config_files:
            table = Table(title="Available Configuration Files")
            table.add_column("File", style="cyan")
            table.add_column("Size", style="green")

            for config_file in config_files:
                size = config_file.stat().st_size
                table.add_row(str(config_file.relative_to(examples_dir)), f"{size} bytes")

            console.print(table)
        else:
            console.print("[yellow]No JSON configuration files found[/yellow]")
    else:
        console.print("[yellow]Example configuration structure:[/yellow]")
        example_config = {
            "name": "Example Jury",
            "criteria": [
                {"name": "factuality", "weight": 2.0, "max_score": 5},
                {"name": "clarity", "weight": 1.5, "max_score": 5}
            ],
            "jurors": [
                {
                    "name": "Expert Juror",
                    "model_name": "openai/gpt-4o-mini",
                    "system_prompt": "You are an expert evaluator.",
                    "weight": 2.0
                }
            ],
            "voting_method": "weighted"
        }
        console.print(json.dumps(example_config, indent=2))


@cli_app.command()
def export_results(
    results_file: Path = typer.Option(..., "--input", "-i", help="Input results JSON file"),
    output_file: Path = typer.Option(..., "--output", "-o", help="Output file path"),
    format: str = typer.Option("csv", "--format", "-f", help="Export format (csv, json, text)"),
):
    if not results_file.exists():
        console.print(f"[red]Error: Results file {results_file} does not exist[/red]")
        raise typer.Exit(1)

    try:
        with open(results_file) as f:
            results = json.load(f)

        if format == "csv":
            import csv
            with open(output_file, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['Response', 'Score', 'Winner', 'Confidence'])
                
                for response_id, score in results.get('scores', {}).items():
                    writer.writerow([
                        response_id,
                        score,
                        results.get('winner', ''),
                        results.get('confidence', 0)
                    ])
        elif format == "json":
            with open(output_file, 'w') as f:
                json.dump(results, f, indent=2)
        elif format == "text":
            with open(output_file, 'w') as f:
                f.write(f"Winner: {results.get('winner', 'N/A')}\n")
                f.write(f"Confidence: {results.get('confidence', 0):.2%}\n\n")
                f.write("Scores:\n")
                for response_id, score in results.get('scores', {}).items():
                    f.write(f"  {response_id}: {score}\n")
        else:
            console.print(f"[red]Error: Unknown format '{format}'[/red]")
            raise typer.Exit(1)

        console.print(f"[green]Results exported to {output_file}[/green]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


def _format_verdict_table(verdict) -> str:
    table = Table(title="Evaluation Results")
    table.add_column("Response", style="cyan")
    table.add_column("Score", style="green")
    table.add_column("Winner", style="yellow")

    for response_id, score in verdict.scores.items():
        is_winner = response_id == verdict.final_verdict.winner
        winner_mark = "🏆" if is_winner else ""
        table.add_row(response_id, str(score), winner_mark)

    console = Console()
    with console.capture() as capture:
        console.print(table)
    return capture.get()


def main():
    cli_app()


if __name__ == "__main__":
    main()