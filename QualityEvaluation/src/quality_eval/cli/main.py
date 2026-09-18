from __future__ import annotations

import argparse
import sys
from pathlib import Path

import quality_eval.operators as builtin_operators
from quality_eval.runtime.executor import WorkflowExecutor
from quality_eval.runtime.loader import WorkflowLoader
from quality_eval.runtime.operator_template import write_operator_template
from quality_eval.runtime.path_security import display_path, resolve_allowed_roots, safe_output_path, safe_path
from quality_eval.runtime.registry import load_custom_operators, registry
from quality_eval.runtime.report import regenerate_markdown_report
from quality_eval.runtime.schema import SchemaValidator

builtin_operators.load_builtin_operators()


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for `quality-eval`.

    Business logic:
        1. Create the top-level `quality-eval` command parser.
        2. Register subcommands for run, report export, config validation, and operator listing.
        3. Bind the existing command-line arguments for each subcommand.

    Args:
        None.

    Returns:
        argparse.ArgumentParser: Parser with all subcommands registered.

    Examples:
        >>> parser = build_parser()
        >>> parser.prog
        'quality-eval'
    """
    parser = argparse.ArgumentParser(prog="quality-eval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a quality evaluation workflow.")
    run_parser.add_argument("-c", "--config", required=True, type=Path, help="Workflow YAML/JSON path.")
    run_parser.add_argument(
        "--task-id",
        default=None,
        help="Task id using letters, numbers, dots, underscores, or hyphens. Auto-generated when omitted.",
    )
    run_parser.add_argument("--output-dir", type=Path, default=None, help="Override configured output directory.")
    run_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint/result files.")
    run_parser.add_argument("--workers", type=int, default=None, help="Override workflow concurrency.")
    run_parser.add_argument("--allow-root", action="append", type=Path, default=[], help="Authorize path access under an existing directory. Repeat for multiple roots.")

    export_parser = subparsers.add_parser("export-report", help="Regenerate Markdown report from a summary JSON.")
    export_parser.add_argument("-t", "--task", required=True, type=Path, help="Run directory or summary JSON path.")
    export_parser.add_argument("-o", "--output", type=Path, default=None, help="Output Markdown path.")
    export_parser.add_argument("--allow-root", action="append", type=Path, default=[], help="Authorize path access under an existing directory. Repeat for multiple roots.")

    validate_parser = subparsers.add_parser("validate-config", help="Validate a workflow config.")
    validate_parser.add_argument("-c", "--config", required=True, type=Path, help="Workflow YAML/JSON path.")
    validate_parser.add_argument("--allow-root", action="append", type=Path, default=[], help="Authorize path access under an existing directory. Repeat for multiple roots.")

    template_parser = subparsers.add_parser("operator-template", help="Generate a custom operator template.")
    template_parser.add_argument("--type", required=True, choices=["text", "image", "score", "governor"], help="Operator template type.")
    template_parser.add_argument("--name", required=True, help="snake_case operator_name used in workflow steps.")
    template_parser.add_argument("--output", required=True, type=Path, help="Output Python file path.")
    template_parser.add_argument("--allow-root", action="append", type=Path, default=[], help="Authorize path access under an existing directory. Repeat for multiple roots.")

    subparsers.add_parser("list-operators", help="List registered operators.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the `quality-eval` command-line entry point.

    Business logic:
        1. Parse command-line arguments and identify the subcommand.
        2. `run` loads the workflow config and executes the evaluation task.
        3. `export-report` regenerates a Markdown report from a summary JSON file.
        4. `validate-config` validates workflow structure, operators, and input paths.
        5. `list-operators` prints all operator names currently registered.

    Args:
        argv (list[str] | None, optional): command-line argument list; reads system arguments when None.

    Returns:
        int: Command exit code. Returns 0 on success and 1 for an unknown command.

    Examples:
        >>> main(["list-operators"])
        0
    """
    parsed_argv = list(sys.argv[1:] if argv is None else argv)
    if parsed_argv and parsed_argv[0] == "validate":
        parsed_argv[0] = "validate-config"
    args = build_parser().parse_args(parsed_argv)
    try:
        if args.command == "run":  # Run the full workflow and print the key output paths.
            allowed_roots = resolve_allowed_roots(args.allow_root)
            config_path = safe_path(args.config, name="workflow config", allowed_roots=allowed_roots)
            output_dir = safe_path(args.output_dir, name="output directory", allowed_roots=allowed_roots) if args.output_dir else None
            config = WorkflowLoader().load(config_path)
            load_custom_operators(
                config.get("custom_operators"),
                base_dir=config_path.parent,
                allowed_roots=allowed_roots,
            )
            executor = WorkflowExecutor(
                config=config,
                config_path=config_path,
                task_id=args.task_id,
                output_dir=output_dir,
                resume=args.resume,
                workers=args.workers,
                allowed_roots=allowed_roots,
            )
            summary = executor.run()
            print(f"task_id={summary['task_id']}")
            print(f"result_path={display_path(summary['paths']['result_path'])}")
            print(f"summary_path={display_path(summary['paths']['summary_path'])}")
            print(f"report_path={display_path(summary['paths']['report_path'])}")
            return 0

        if args.command == "export-report":  # Regenerate a Markdown report from an existing summary file.
            allowed_roots = resolve_allowed_roots(args.allow_root)
            task_path = safe_path(args.task, name="task", allowed_roots=allowed_roots)
            report_output_path = safe_output_path(args.output, name="report output", allowed_roots=allowed_roots) if args.output else None
            report_path = regenerate_markdown_report(task_path, report_output_path)
            print(f"report_path={display_path(report_path)}")
            return 0

        if args.command == "validate-config":  # Validate structure, operator registration, and real input paths together.
            return _validate_config_command(args, resolve_allowed_roots(args.allow_root))

        if args.command == "operator-template":  # Generate a commented custom operator template.
            allowed_roots = resolve_allowed_roots(args.allow_root)
            template_output_path = safe_output_path(args.output, name="operator template output", allowed_roots=allowed_roots)
            path = write_operator_template(args.type, args.name, template_output_path)
            print(f"created: {display_path(path)}")
            return 0

        if args.command == "list-operators":  # Show registry contents to verify operators were imported successfully.
            for name in registry.names():  # Output operator names in registry order for stable results.
                print(name)
            return 0
    except (ValueError, FileNotFoundError, KeyError, ImportError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    return 1


def _validate_config_command(args: argparse.Namespace, allowed_roots: tuple[Path, ...] | None = None) -> int:
    """Validate structure, operator registration, and real input paths together."""
    config_path = safe_path(args.config, name="workflow config", allowed_roots=allowed_roots)
    config = WorkflowLoader().load(config_path)
    load_custom_operators(
        config.get("custom_operators"),
        base_dir=config_path.parent,
        allowed_roots=allowed_roots,
    )
    validator = SchemaValidator()
    validator.validate_config(config, registry=registry)

    base_dir = config_path.parent.resolve()
    project_dir = base_dir.parent if base_dir.name == "workflows" else base_dir

    def resolve_path(value: str | Path) -> Path:
        """Resolve relative paths based on the workflow file location."""
        resolved = safe_path(value, name="workflow path", base_dir=base_dir, allowed_roots=allowed_roots)
        if resolved.exists():  # Prefer local references next to the workflow file when they exist.
            return resolved
        fallback = safe_path(value, name="workflow path", base_dir=project_dir, allowed_roots=allowed_roots)
        return resolved if fallback == resolved else fallback

    validator.validate_paths(config, resolve_path)
    print(f"valid_config={display_path(config_path)}")
    return 0
