from __future__ import annotations

import json
import sys
from pathlib import Path

import click

import synthesis_engine.operators  # noqa: F401 - registers built-in operators
from synthesis_engine.runtime.config import load_workflow_config
from synthesis_engine.runtime.executor import WorkflowExecutor
from synthesis_engine.runtime.input_adapter import InputAdapter
from synthesis_engine.runtime.operator_template import write_operator_template
from synthesis_engine.runtime.registry import load_custom_operators, registry


@click.group()
def cli() -> None:
    """Provide the command-line entry point for the data synthesis workflow

    Business logic:
        1. Register commands for workflow validation, execution, reporting, and tracing
        2. Delegate subcommand dispatch to Click

    Args:
        None.

    Returns:
        None: Does not return business data directly.

    Examples:
        >>> cli.name
        'cli'
    """


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True))
def validate(config_path: str) -> None:
    """Validate workflow configuration and operator creatability

    Business logic:
        1. Read the specified workflow config file
        2. Instantiate each configured operator to validate the registry
        3. Print confirmation that the config is usable

    Args:
        config_path (str): Workflow config file path.

    Returns:
        None: Returns validation results through standard output.

    Examples:
        >>> validate.callback is None
        False
    """
    config_file = Path(config_path).resolve()
    config = load_workflow_config(config_file)
    load_custom_operators(config.custom_operators, base_dir=config_file.parent)
    InputAdapter(config.input.__dict__, config_file.parent.parent).validate_config()
    for step in config.steps:  # Validate step by step that every declared operator can be instantiated.
        registry.create(step.operator, step.params)
    click.echo(f"OK: {config.workflow.id} ({len(config.steps)} steps)")


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--resume", is_flag=True, help="Resume from the configured output.path directory.")
def run(config_path: str, resume: bool) -> None:
    """Run the specified workflow configuration

    Business logic:
        1. Resolve the absolute workflow config path
        2. Load the config and create the executor
        3. Execute the workflow and print the configured output directory

    Args:
        config_path (str): Workflow config file path.
        resume (bool): Whether to resume from output.path and skip accepted samples.

    Returns:
        None: Returns the output directory through standard output.

    Examples:
        >>> run.callback is None
        False
    """
    config_file = Path(config_path).resolve()
    config = load_workflow_config(config_file)
    load_custom_operators(config.custom_operators, base_dir=config_file.parent)
    output_dir = WorkflowExecutor(config, config_file, resume=resume).run()
    click.echo(str(output_dir))


@cli.command("operator-template")
@click.option("--type", "operator_type", required=True, type=click.Choice(["text", "image", "structured", "quality_gate"]))
@click.option("--name", required=True)
@click.option("--output", required=True, type=click.Path())
def operator_template(operator_type: str, name: str, output: str) -> None:
    """Generate a template for a user-defined synthesis operator

    Business logic:
        1. Accept the operator type, registry name, and output path
        2. Generate a commented GenerationItem operator template
        3. Print the template path for custom_operators configuration

    Args:
        operator_type (str): Custom operator type.
        name (str): operator_name used in the workflow.
        output (str): Template output path.

    Returns:
        None: Returns the generated path through standard output.

    Examples:
        >>> operator_template.callback is None
        False
    """
    try:
        output_path = write_operator_template(operator_type, name, Path(output))
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"operator_template={output_path}")


@cli.command()
@click.option("-t", "--task", "task_path", required=True, type=click.Path())
def report(task_path: str) -> None:
    """Print the Markdown report for a specified run directory

    Business logic:
        1. Resolve the task path into the actual run directory
        2. Locate report.md under the run directory
        3. Safely print the report text

    Args:
        task_path (str): Run directory path or the latest shortcut path.

    Returns:
        None: Returns report content through standard output.

    Examples:
        >>> report.callback is None
        False
    """
    run_dir = _resolve_run_dir(task_path)
    report_path = run_dir / "report.md"
    if not report_path.exists():  # Give a command-line-facing clear error when the report is missing.
        raise click.ClickException(f"Report not found: {report_path}")
    _safe_echo(report_path.read_text(encoding="utf-8"))


@cli.command()
@click.option("--sample-id", required=True)
@click.option("-t", "--task", "task_path", required=True, type=click.Path())
def trace(sample_id: str, task_path: str) -> None:
    """Trace the generated or filtered result for a specified sample

    Business logic:
        1. Resolve the run directory and locate output JSONL files
        2. Search line by line for a matching sample id
        3. Print formatted JSON when found, otherwise report the missing sample

    Args:
        sample_id (str): Sample id to query.
        task_path (str): Run directory path or the latest shortcut path.

    Returns:
        None: Returns sample JSON through standard output.

    Examples:
        >>> trace.callback is None
        False
    """
    run_dir = _resolve_run_dir(task_path)
    generated_path = run_dir / "generated.jsonl"
    filtered_path = run_dir / "filtered.jsonl"
    for path in [generated_path, filtered_path]:  # Search both accepted and filtered outputs to cover the full sample lifecycle.
        if not path.exists():  # Some output classes may be absent, so skip missing files and continue.
            continue
        for line in path.read_text(encoding="utf-8").splitlines():  # Parse JSONL line by line to locate the sample.
            item = json.loads(line)
            if item.get("id") == sample_id:  # Print immediately and stop scanning after the target sample is found.
                _safe_echo(json.dumps(item, ensure_ascii=False, indent=2))
                return
    raise click.ClickException(f"Sample not found: {sample_id}")


def _resolve_run_dir(task_path: str) -> Path:
    """Resolve a run directory path or the latest shortcut path

    Business logic:
        1. Convert the input path to an absolute path
        2. When the path name is latest, select the newest run directory under its parent
        3. Otherwise return the input path directly

    Args:
        task_path (str): Run directory path or the latest shortcut path.

    Returns:
        Path: Actual run directory path.

    Examples:
        >>> _resolve_run_dir('/tmp/run').name
        'run'
    """
    path = Path(task_path).resolve()
    if path.name == "latest":  # Use latest as a command-line shortcut for the most recent run directory.
        parent = path.parent
        runs = sorted([child for child in parent.iterdir() if child.is_dir()])
        if not runs:  # Return a clear error when no historical run directories exist.
            raise click.ClickException(f"No run directories found under {parent}")
        return runs[-1]
    return path


def _safe_echo(text: str) -> None:
    """Print text safely using the terminal encoding

    Business logic:
        1. Read stdout encoding and default to utf-8
        2. Replace characters that cannot be encoded
        3. Let Click print the processed text

    Args:
        text (str): Text to print.

    Returns:
        None: Produces only a standard-output side effect.

    Examples:
        >>> _safe_echo('')
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    click.echo(safe_text)


if __name__ == "__main__":
    cli()
