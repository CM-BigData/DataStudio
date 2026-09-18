from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from denoise_workflow_engine.runtime.executor import WorkflowExecutor
from denoise_workflow_engine.runtime.env import load_local_env
from denoise_workflow_engine.runtime.input_adapter import InputAdapter
from denoise_workflow_engine.runtime.loader import load_workflow_config, resolve_allowed_roots, resolve_path
from denoise_workflow_engine.runtime.operator_template import write_operator_template
from denoise_workflow_engine.runtime.registry import build_default_registry


def run_command(args: argparse.Namespace) -> int:
    """Run a workflow configuration and print a short execution summary.

    Business logic:
        1. Load local API environment variables so model-based operators can read credentials.
        2. Load the workflow configuration and create the default operator registry.
        3. Execute the workflow and print the workflow ID, counts, and report path.

    Args:
            args (argparse.Namespace): Parsed argparse namespace.

    Returns:
        int: command-line exit code.

    Examples:
        >>> run_command
        run_command
    """
    load_local_env()
    allowed_roots = resolve_allowed_roots(args.allow_root)
    config_path = resolve_path(
        args.config,
        Path.cwd(),
        allowed_roots=allowed_roots,
        name="workflow config",
    )
    config = load_workflow_config(config_path)  # Workflow configuration holding thresholds and API settings.
    if args.resume:  # Explicit command-line resume takes precedence over workflow defaults.
        config.setdefault("workflow", {})["resume"] = True
        config["workflow"]["checkpoint"] = True
    workflow_base_dir = config_path.parent
    registry = build_default_registry(
        config.get("custom_operators", []),
        base_dir=workflow_base_dir,
        allowed_roots=allowed_roots,
    )  # Registry used to instantiate operators by name.
    executor = WorkflowExecutor(
        config=config,
        registry=registry,
        base_dir=workflow_base_dir,
        allowed_roots=allowed_roots,
    )
    summary = executor.run()
    print(f"workflow_id={summary['workflow_id']}")
    print(f"total={summary['total_count']} keep={summary['keep_count']} drop={summary['drop_count']} review={summary['review_count']} failed={summary['failed_count']}")
    print(f"report={summary['report_path']}")
    return 0


def validate_command(args: argparse.Namespace) -> int:
    """Validate workflow structure and operator references.

    Business logic:
        1. Check for required top-level sections.
        2. Validate section types and input configuration shape.
        3. Instantiate operator references early to expose unknown names before execution.

    Args:
            args (argparse.Namespace): Parsed argparse namespace.

    Returns:
        int: command-line exit code.

    Examples:
        >>> validate_command
        validate_command
    """
    load_local_env()
    allowed_roots = resolve_allowed_roots(args.allow_root)
    config_path = resolve_path(
        args.config,
        Path.cwd(),
        allowed_roots=allowed_roots,
        name="workflow config",
    )
    config = load_workflow_config(config_path)  # Workflow configuration holding thresholds and API settings.
    workflow_base_dir = config_path.parent
    registry = build_default_registry(
        config.get("custom_operators", []),
        base_dir=workflow_base_dir,
        allowed_roots=allowed_roots,
    )  # Registry used to instantiate operators by name.
    required = ["workflow", "input", "output", "steps"]
    missing = [key for key in required if key not in config]
    if missing:  # Missing top-level sections prevent the executor from locating inputs, outputs, or steps.
        print(f"invalid workflow config, missing: {', '.join(missing)}", file=sys.stderr)
        return 2
    for section in required[:3]:  # workflow, input, and output must be objects.
        if not isinstance(config.get(section), dict):  # Reject invalid section types early.
            print(f"invalid workflow config, section must be object: {section}", file=sys.stderr)
            return 2
    try:
        InputAdapter(config["input"], workflow_base_dir, allowed_roots=allowed_roots).validate_config()
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not isinstance(config.get("steps"), list) or not config["steps"]:  # Steps must be a non-empty list.
        print("invalid workflow config, steps must be a non-empty list", file=sys.stderr)
        return 2
    for step in config["steps"]:  # Validate each workflow step one by one.
        if not isinstance(step, dict) or "id" not in step or "operator" not in step:  # Reject malformed step definitions.
            print(f"invalid step: {step}", file=sys.stderr)
            return 2
        try:
            registry.create(step["operator"], step.get("params", {}))
        except KeyError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    print("workflow config is valid")
    return 0


def report_command(args: argparse.Namespace) -> int:
    """Read a run directory and print a metrics summary.

    Business logic:
        1. Locate `metrics.json` and `report.md` in the run directory.
        2. Print summary counts for total, keep, drop, review, and failed items.
        3. Optionally print the full Markdown report when `--show` is enabled.

    Args:
            args (argparse.Namespace): Parsed argparse namespace.

    Returns:
        int: command-line exit code.

    Examples:
        >>> report_command
        report_command
    """
    run_dir = args.run_dir
    metrics_path = run_dir / "metrics.json"
    report_path = run_dir / "report.md"
    if not metrics_path.exists():  # Missing metrics indicates the directory is not a complete workflow run.
        print(f"metrics not found: {metrics_path}", file=sys.stderr)
        return 2
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    print(f"workflow_id={metrics.get('workflow_id')}")
    print(
        "total={total_count} keep={keep_count} drop={drop_count} review={review_count} failed={failed_count}".format(
            **metrics
        )
    )
    print(f"report={report_path}")
    if args.show and report_path.exists():  # Print the report only when the file exists.
        print(report_path.read_text(encoding="utf-8"))
    return 0


def operator_template_command(args: argparse.Namespace) -> int:
    """Generate a template file for a custom operator.

    Business logic:
        1. Read the requested operator type, registration name, and output path.
        2. Generate a commented `BaseOperator` subclass template.
        3. Print the template path so the user can add it to `workflow.custom_operators`.

    Args:
        args (argparse.Namespace): Parsed argparse namespace.

    Returns:
        int: command-line exit code.

    Examples:
        >>> callable(operator_template_command)
        True
    """
    try:
        output_path = write_operator_template(args.type, args.name, args.output)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"operator_template={output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command-line parser for the `denoise` command.

    Business logic:
        1. Create the top-level parser.
        2. Register the `run`, `validate`, `report`, and `operator-template` subcommands.
        3. Bind each subcommand to its handler function.

    Args:
            None: This function does not take input parameters.

    Returns:
        argparse.ArgumentParser: Fully configured command-line parser.

    Examples:
        >>> build_parser
        build_parser
    """
    parser = argparse.ArgumentParser(prog="denoise", description="Run denoise workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a denoise workflow.")
    run_parser.add_argument("-c", "--config", required=True, type=Path, help="Path to workflow config.")
    run_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint and existing outputs.")
    run_parser.add_argument(
        "--allow-root",
        action="append",
        type=Path,
        default=[],
        help="Authorize path access under an existing directory. Repeat for multiple roots.",
    )
    run_parser.set_defaults(func=run_command)

    validate_parser = subparsers.add_parser("validate", help="Validate a workflow config.")
    validate_parser.add_argument("-c", "--config", required=True, type=Path, help="Path to workflow config.")
    validate_parser.add_argument(
        "--allow-root",
        action="append",
        type=Path,
        default=[],
        help="Authorize path access under an existing directory. Repeat for multiple roots.",
    )
    validate_parser.set_defaults(func=validate_command)

    report_parser = subparsers.add_parser("report", help="Show a finished run report summary.")
    report_parser.add_argument("-t", "--run-dir", required=True, type=Path, help="Run directory containing metrics.json.")
    report_parser.add_argument("--show", action="store_true", help="Print report.md contents.")
    report_parser.set_defaults(func=report_command)

    template_parser = subparsers.add_parser("operator-template", help="Generate a custom operator template.")
    template_parser.add_argument(
        "--type",
        required=True,
        choices=["text_denoise", "image_denoise", "video_denoise", "image_text_pair_denoise", "auto_denoise"],
        help="Custom end-to-end operator type.",
    )
    template_parser.add_argument("--name", required=True, help="snake_case operator_name used in workflow steps.")
    template_parser.add_argument("--output", required=True, type=Path, help="Output Python file path.")
    template_parser.set_defaults(func=operator_template_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse command-line arguments and dispatch to the selected subcommand.

    Business logic:
        1. Build the command-line parser.
        2. Parse the provided `argv` or process command-line arguments.
        3. Call the resolved subcommand function and return its exit code.

    Args:
            argv (list[str] | None): Optional command-line argument list.

    Returns:
        int: command-line exit code.

    Examples:
        >>> main
        main
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
