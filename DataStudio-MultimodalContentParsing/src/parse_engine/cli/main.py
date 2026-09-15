from __future__ import annotations

import json
import sys
from pathlib import Path

import click

import parse_engine.operators  # noqa: F401 - registers built-in operators
from parse_engine.runtime.config import load_workflow_config
from parse_engine.runtime.executor import WorkflowExecutor
from parse_engine.runtime.input_adapter import InputAdapter
from parse_engine.runtime.operator_template import write_operator_template
from parse_engine.runtime.registry import load_custom_operators, registry


@click.group()
def cli() -> None:
    """Command entrypoint for the multimodal content parsing workflow.

    Business logic:
        1. Create a Click command group and attach the validate, run, report, and trace subcommands.
        2. Do not execute parsing logic directly; only dispatch commands.
        3. Let concrete subcommands load config, run the workflow, or inspect execution results.

    Args:
        None.

    Returns:
        None: The Click command group callback does not return business data.

    Examples:
        >>> cli.name is None or isinstance(cli.name, str)
        True"""


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True))
def validate(config_path: str) -> None:
    """Validate that workflow configuration and operator references can be instantiated.

    Business logic:
        1. Load workflow configuration from the specified YAML file.
        2. Traverse each configured step and instantiate the corresponding operator through the registry.
        3. Output the workflow id and step count when all operators can be created.

    Args:
        config_path (str): Workflow configuration file path. It must point to an existing file.

    Returns:
        None: Validation results are reported through standard output or a Click exception.

    Examples:
        >>> isinstance("workflows/pdf_parse.yaml", str)
        True"""
    config = load_workflow_config(config_path)
    config_file = Path(config_path).resolve()
    load_custom_operators(config.custom_operators, base_dir=config_file.parent)
    InputAdapter(config.input.model_dump(exclude_none=True), base_dir=config_file.parent.parent).validate_config()
    for step in config.steps:  # Confirm that every configured operator can be instantiated from the registry.
        registry.create(step.operator, step.params)
    click.echo(f"OK: {config.workflow.id} ({len(config.steps)} steps)")


@cli.command()
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True))
@click.option("--resume", is_flag=True, help="Resume from the configured output.path directory.")
def run(config_path: str, resume: bool) -> None:
    """Run a content parsing workflow once with the given configuration.

    Business logic:
        1. Resolve the absolute config file path and load the workflow configuration.
        2. Build a WorkflowExecutor to load inputs, run the operator pipeline, and write outputs.
        3. Output the configured output directory path to the caller.

        Args:
        config_path (str): Workflow configuration file path. It must point to an existing file.
        resume (bool): Whether to resume from output.path and skip completed samples.

    Returns:
        None: The output directory is returned through standard output.

    Examples:
        >>> isinstance("workflows/word_parse.yaml", str)
        True"""
    config_file = Path(config_path).resolve()
    config = load_workflow_config(config_file)
    load_custom_operators(config.custom_operators, base_dir=config_file.parent)
    executor = WorkflowExecutor(config, config_file, resume=resume)
    output_dir = executor.run()
    click.echo(str(output_dir))


@cli.command("operator-template")
@click.option("--type", "operator_type", required=True, type=click.Choice(["document", "image", "audio", "text", "quality_gate"]))
@click.option("--name", "operator_name", required=True, help="snake_case operator_name used in workflow steps.")
@click.option("--output", "output_path", required=True, type=click.Path())
def operator_template(operator_type: str, operator_name: str, output_path: str) -> None:
    """Generate a template for a user-defined parsing operator.

    Business logic:
        1. Accept the operator type, registry name, and output path.
        2. Render a Python template with input/output contract comments.
        3. Write the file and output the resulting path.

    Args:
        operator_type (str): Template operator type.
        operator_name (str): snake_case operator name referenced in the workflow.
        output_path (str): Output path for the template Python file.

    Returns:
        None: The template path is returned through standard output.

    Examples:
        >>> isinstance("my_parse_operator", str)
        True"""
    path = write_operator_template(operator_type, operator_name, Path(output_path))
    click.echo(f"created: {path}")


@cli.command()
@click.option("-t", "--task", "task_path", required=True, type=click.Path())
def report(task_path: str) -> None:
    """Print the Markdown report in the specified run directory.

    Business logic:
        1. Resolve the task path to the real run directory, including the latest alias.
        2. Check whether report.md exists and raise a Click exception if it does not.
        3. Print the report text with a safe output helper to avoid terminal encoding errors.

    Args:
        task_path: Run directory path, or a latest-run alias such as outputs/latest.

    Returns:
        None: Report content is printed through standard output.

    Examples:
        >>> isinstance("reports/latest", str)
        True"""
    run_dir = _resolve_run_dir(task_path)
    report_path = run_dir / "report.md"
    if not report_path.exists():  # Tell the caller that the task directory is not a valid run result.
        raise click.ClickException(f"Report not found: {report_path}")
    _safe_echo(report_path.read_text(encoding="utf-8"))


@cli.command()
@click.option("--sample-id", required=True)
@click.option("-t", "--task", "task_path", required=True, type=click.Path())
def trace(sample_id: str, task_path: str) -> None:
    """Look up parsing results by sample id or artifact id.

    Business logic:
        1. Resolve the task path to the run directory and locate artifacts.jsonl.
        2. Read sample results line by line, matching sample id first and artifact id second.
        3. Output formatted JSON when found, or raise a Click exception when not found.

    Args:
        sample_id: Sample id or artifact id to query.
        task_path: Run directory path containing artifacts.jsonl, or a latest alias.

    Returns:
        None: Matching results are printed through standard output.

    Examples:
        >>> "demo_page_1_text".endswith("text")
        True"""
    run_dir = _resolve_run_dir(task_path)
    artifacts_path = run_dir / "artifacts.jsonl"
    if not artifacts_path.exists():  # Tracing is impossible without sample or artifact records.
        raise click.ClickException(f"artifacts.jsonl not found: {artifacts_path}")

    for line in artifacts_path.read_text(encoding="utf-8").splitlines():  # Inspect sample records one by one.
        item = json.loads(line)
        if item.get("id") == sample_id:  # Return the full sample record directly.
            _safe_echo(json.dumps(item, ensure_ascii=False, indent=2))
            return
        for artifact in item.get("artifacts", []):  # Search for the artifact id within the current sample.
            if artifact.get("id") == sample_id:  # Return only the matching artifact.
                _safe_echo(json.dumps(artifact, ensure_ascii=False, indent=2))
                return
    raise click.ClickException(f"Sample or artifact not found: {sample_id}")


def _resolve_run_dir(task_path: str) -> Path:
    """Resolve the run directory path from command-line input.

    Business logic:
        1. Convert the incoming path to an absolute path.
        2. When the path name is latest, scan all run directories under the parent and choose the last sorted one.
        3. Return ordinary paths unchanged as run directories.

    Args:
        task_path: Run directory path or latest alias path provided by the user.

    Returns:
        Path: Absolute run directory path that should actually be read.

    Examples:
        >>> _resolve_run_dir(".").is_absolute()
        True"""
    path = Path(task_path).resolve()
    if path.name == "latest":  # Resolve to the latest run directory under the parent directory.
        parent = path.parent
        runs = sorted([child for child in parent.iterdir() if child.is_dir()])
        if not runs:  # latest cannot be mapped to an actual directory.
            raise click.ClickException(f"No run directories found under {parent}")
        return runs[-1]
    return path


def _safe_echo(text: str) -> None:
    """Safely print text using the current terminal encoding.

    Business logic:
        1. Read the standard output encoding and fall back to utf-8 when it is missing.
        2. Re-encode the text with the replace strategy so unsupported characters are substituted safely.
        3. Output the processed text through click.echo.

    Args:
        text: Text content that needs to be printed to the terminal.

    Returns:
        None: The text is written directly to standard output.

    Examples:
        >>> isinstance("Content Parsing Report", str)
        True"""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    click.echo(safe_text)


if __name__ == "__main__":
    cli()
