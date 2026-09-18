from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dedup_workflow_engine.runtime.executor import WorkflowExecutor
from dedup_workflow_engine.runtime.env import load_local_env_files
from dedup_workflow_engine.runtime.input_adapter import InputAdapter
from dedup_workflow_engine.runtime.loader import load_workflow_config
from dedup_workflow_engine.runtime.operator_template import write_operator_template
from dedup_workflow_engine.runtime.registry import build_default_registry, load_custom_operators
from dedup_workflow_engine.runtime.router import (
    build_routed_workflow_config,
    load_and_route_input,
    workflow_path_for_modality,
    write_jsonl,
)


def _display_path(path_value: object) -> str:
    """Return a path string suitable for command-line display."""
    path = Path(str(path_value))
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except (OSError, ValueError):
        return path.name if path.name else "[external-path]"


def run_command(args: argparse.Namespace) -> int:
    """Run the `dedup run` subcommand.

    Business logic:
        1. Load workflow config from the path specified by -c/--config.
        2. Reuse run_config to execute the workflow.
        3. Return the run_config process exit code to the command-line.

    Args:
        args (argparse.Namespace): Parsed argparse parameters for the run subcommand.

    Returns:
        int: Process exit code; 0 means success.

    Examples:
        >>> run_command(argparse.Namespace(config="workflow.yaml"))  # doctest: +SKIP
        0
    """
    config = load_workflow_config(Path(args.config))
    if args.resume:  # Explicit command-line resume overrides the workflow's default runtime setting.
        config.setdefault("runtime", {})["resume"] = True
        config["runtime"]["checkpoint"] = True
    return run_config(config, base_dir=Path(args.config).resolve().parent)


def run_config(config: dict, base_dir: Path | None = None) -> int:
    """Run a loaded workflow config and print a summary.

    Business logic:
        1. Build the default operator registry.
        2. Create a WorkflowExecutor and execute the workflow.
        3. Print workflow_id, sample counts, and report path.

    Args:
        config (dict): Parsed workflow config.
        base_dir (Path | None, optional): Base directory for resolving relative custom_operators paths.

    Returns:
        int: Process exit code; 0 means success.

    Examples:
        >>> run_config({"workflow": {}, "input": {}, "output": {}, "steps": []})  # doctest: +SKIP
        0
    """
    registry = build_default_registry()
    load_custom_operators(registry, config.get("custom_operators"), base_dir=base_dir)
    executor = WorkflowExecutor(config=config, registry=registry)
    summary = executor.run()
    print(f"workflow_id={summary['workflow_id']}")
    print(
        "total={total_count} kept={kept_count} removed={removed_count} review={review_count} "
        "groups={duplicate_group_count}".format(**summary)
    )
    print(f"report={_display_path(summary['report_path'])}")
    return 0


def auto_run_command(args: argparse.Namespace) -> int:
    """Run the `dedup auto-run` subcommand.

    Business logic:
        1. Load mixed input and bucket samples by modality.
        2. Select a workflow template and output directory for each matching modality.
        3. Run each modality workflow and write summary.json.

    Args:
        args (argparse.Namespace): Parsed argparse parameters for auto-run.

    Returns:
        int: Process exit code; 0 for success and 1 when no runnable input exists.

    Examples:
        >>> auto_run_command(argparse.Namespace(input="in.jsonl", output_dir="runs", workflow_dir="workflows", profile="strict", modality="auto"))  # doctest: +SKIP
        0
    """
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    workflow_dir = Path(args.workflow_dir)
    routed = load_and_route_input(input_path)
    if not routed:  # Stop auto-run when the input file has no recognizable samples.
        print(f"no valid input items found: {input_path}", file=sys.stderr)
        return 1

    summaries = []
    for modality, items in routed.items():  # Run the matching workflow independently for each modality bucket.
        if args.modality != "auto" and modality != args.modality:  # Skip other buckets when the user forces one modality.
            continue
        routed_input = input_path
        run_dir = output_dir / modality
        if len(routed) > 1:  # Split multimodal input into temporary JSONL files so single-modality workflows do not read other modalities.
            routed_input = output_dir / "_routed_inputs" / f"{modality}.jsonl"
            write_jsonl(routed_input, items)
        template_path = workflow_path_for_modality(workflow_dir, modality, args.profile)
        config = build_routed_workflow_config(template_path, routed_input, run_dir)
        if args.resume:  # Pass resume through to each modality-specific child workflow.
            config.setdefault("runtime", {})["resume"] = True
            config["runtime"]["checkpoint"] = True
        summary = _run_workflow_and_return_summary(config)
        summaries.append(summary)
        print(
            "modality={modality} total={total_count} kept={kept_count} removed={removed_count} "
            "review={review_count} groups={duplicate_group_count}".format(**summary)
        )

    if not summaries:  # Routing succeeded but no samples matched the user-requested modality.
        print(f"no input items matched modality: {args.modality}", file=sys.stderr)
        return 1
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps({"runs": summaries}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"summary={_display_path(summary_path)}")
    return 0


def _run_workflow_and_return_summary(config: dict) -> dict:
    """Run one routed workflow and return its summary.

    Business logic:
        1. Create the default operator registry for this workflow.
        2. Run the config with WorkflowExecutor.
        3. Return the run summary generated by the executor.

    Args:
        config (dict): Workflow config with injected input path and run_dir.

    Returns:
        dict: Run summary returned by the executor.

    Examples:
        >>> _run_workflow_and_return_summary({})  # doctest: +SKIP
        {'workflow_id': 'demo'}
    """
    registry = build_default_registry()
    load_custom_operators(registry, config.get("custom_operators"))
    executor = WorkflowExecutor(config=config, registry=registry)
    return executor.run()


def validate_command(args: argparse.Namespace) -> int:
    """Run the `dedup validate` subcommand.

    Business logic:
        1. Load the workflow config file.
        2. Validate that workflow, input, output, and steps sections exist.
        3. Validate that steps is a non-empty list and print the result.

    Args:
        args (argparse.Namespace): Parsed argparse parameters for validate.

    Returns:
        int: 0 when the config is valid and 2 when it is invalid.

    Examples:
        >>> validate_command(argparse.Namespace(config="workflow.yaml"))  # doctest: +SKIP
        0
    """
    config = load_workflow_config(Path(args.config))
    required = ["workflow", "input", "output", "steps"]
    missing = [key for key in required if key not in config]
    if missing:  # The workflow cannot start when required top-level sections are missing.
        print(f"invalid workflow config, missing: {', '.join(missing)}", file=sys.stderr)
        return 2
    if not isinstance(config.get("steps"), list) or not config["steps"]:  # Steps must contain at least one executable operator step.
        print("invalid workflow config, steps must be a non-empty list", file=sys.stderr)
        return 2
    registry = build_default_registry()
    config_path = Path(args.config).resolve()
    load_custom_operators(registry, config.get("custom_operators"), base_dir=config_path.parent)
    InputAdapter(config.get("input", {}), base_dir=Path.cwd()).validate_config()
    for step in config["steps"]:  # Confirm every configured operator can be created.
        registry.create(str(step["operator"]), config=dict(step.get("params", {})))
    print("workflow config is valid")
    return 0


def operator_template_command(args: argparse.Namespace) -> int:
    """Run the `dedup operator-template` subcommand.

    Business logic:
        1. Accept the operator type, registration name, and output path.
        2. Render a Python template with input/output contract comments.
        3. Write the file and print its path.

    Args:
        args (argparse.Namespace): Parsed argparse parameters for operator-template.

    Returns:
        int: 0 when the template is generated successfully.

    Examples:
        >>> operator_template_command(argparse.Namespace(type="text", name="my_operator", output="x.py"))  # doctest: +SKIP
        0
    """
    path = write_operator_template(args.type, args.name, Path(args.output))
    print(f"created: {path}")
    return 0


def inspect_group_command(args: argparse.Namespace) -> int:
    """Run the `dedup inspect-group` subcommand.

    Business logic:
        1. Search for the duplicate group in the specified run_dir or the default runs directory.
        2. Return exit code 1 when it is not found.
        3. Output the full group as JSON when it is found.

    Args:
        args (argparse.Namespace): Parsed argparse parameters for inspect-group.

    Returns:
        int: 0 when the group is found and 1 otherwise.

    Examples:
        >>> inspect_group_command(argparse.Namespace(group_id="g1", run_dir=None))  # doctest: +SKIP
        0
    """
    group = _find_group(args.group_id, Path(args.run_dir) if args.run_dir else None)
    if not group:  # Preserve stderr output and a non-zero exit code when the group is not found.
        print(f"group not found: {args.group_id}", file=sys.stderr)
        return 1
    print(json.dumps(group, ensure_ascii=False, indent=2))
    return 0


def inspect_item_command(args: argparse.Namespace) -> int:
    """Run the `dedup inspect-item` subcommand.

    Business logic:
        1. Search for the specified item id in the input file and run output files.
        2. Find duplicate groups containing that item.
        3. Output either the full record or a summary based on verbose.

    Args:
        args (argparse.Namespace): Parsed argparse parameters for inspect-item.

    Returns:
        int: 0 when the item or related groups are found and 1 when nothing is found.

    Examples:
        >>> inspect_item_command(argparse.Namespace(item_id="x", run_dir="run", input=None, verbose=False, max_text_chars=20))  # doctest: +SKIP
        0
    """
    run_dir = Path(args.run_dir)
    item_id = args.item_id
    input_item = _find_item_in_jsonl(item_id, Path(args.input)) if args.input else None
    output_item = _find_item_in_run_outputs(item_id, run_dir)
    groups = _find_groups_for_item(item_id, run_dir)
    result = {
        "item_id": item_id,
        "input": input_item if args.verbose else _summarize_item(input_item, args.max_text_chars),
        "output": output_item if args.verbose else _summarize_item(output_item, args.max_text_chars),
        "duplicate_groups": groups if args.verbose else [_summarize_group(group) for group in groups],
    }
    if not result["input"] and not result["output"] and not result["duplicate_groups"]:  # Treat the item as missing only when all three sources are empty.
        print(f"item not found: {item_id}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _summarize_item(item: dict | None, max_text_chars: int) -> dict | None:
    """Build an item summary suitable for command-line display.

    Business logic:
        1. Return None immediately when the item is empty.
        2. Copy payload and truncate text using max_text_chars.
        3. Return commonly used troubleshooting fields to avoid overly long default output.

    Args:
        item (dict | None): Sample record from input or output.
        max_text_chars (int): Maximum number of characters to display for text payload.

    Returns:
        dict | None: Item summary, or None when the input item is empty.

    Examples:
        >>> _summarize_item({"id": "1", "payload": {"text": "abcdef"}}, 3)["payload"]["text"]
        'abc...[truncated]'
    """
    if not item:  # Callers are allowed to have a missing input record.
        return None
    payload = dict(item.get("payload", {}))
    if "text" in payload:  # Text samples may be long, so the default summary should truncate them.
        payload["text"] = _clip_for_display(str(payload["text"]), max_text_chars)
    return {
        "id": item.get("id"),
        "modality": item.get("modality"),
        "payload": payload,
        "action": item.get("action"),
        "issues": item.get("issues", []),
        "metrics": item.get("metrics", {}),
        "output_file": item.get("output_file"),
    }


def _summarize_group(group: dict) -> dict:
    """Build a command-line summary for one duplicate group.

    Business logic:
        1. Read the group id and member ids.
        2. Preserve keep/remove decision fields.
        3. Preserve score and reasons so the duplicate decision can be explained.

    Args:
        group (dict): Full duplicate-group record.

    Returns:
        dict: Duplicate-group summary.

    Examples:
        >>> _summarize_group({"group_id": "g", "member_ids": ["a"]})["group_id"]
        'g'
    """
    return {
        "group_id": group.get("group_id"),
        "member_ids": group.get("member_ids", []),
        "keep_id": group.get("keep_id"),
        "remove_ids": group.get("remove_ids", []),
        "score": group.get("score"),
        "reasons": group.get("reasons", []),
    }


def _clip_for_display(text: str, max_chars: int) -> str:
    """Truncate text to a command-line-friendly display length.

    Business logic:
        1. Do not truncate when max_chars is less than or equal to 0.
        2. Return the original text when it does not exceed the limit.
        3. Truncate long text and append a truncated marker.

    Args:
        text (str): Text to display.
        max_chars (int): Maximum number of characters to display.

    Returns:
        str: Original text or its truncated display form.

    Examples:
        >>> _clip_for_display("abcdef", 3)
        'abc...[truncated]'
    """
    if max_chars <= 0 or len(text) <= max_chars:  # A non-positive limit means full display, and short text does not need truncation.
        return text
    return text[:max_chars] + "...[truncated]"


def _find_group(group_id: str, run_dir: Path | None) -> dict | None:
    """Find a specific duplicate group.

    Business logic:
        1. Search only the specified run's duplicate_groups.jsonl when run_dir is provided.
        2. Otherwise search runs/*/duplicate_groups.jsonl in descending modification-time order.
        3. Add run_dir to the matched record and return it.

    Args:
        group_id (str): Duplicate-group id to find.
        run_dir (Path | None): Specific run directory, or None to search the default runs directory.

    Returns:
        dict | None: Matched group, or None when not found.

    Examples:
        >>> _find_group("missing", Path("missing-run")) is None
        True
    """
    paths: list[Path] = []
    if run_dir:  # Avoid cross-run confusion for same-named groups when run_dir is specified.
        paths = [run_dir / "duplicate_groups.jsonl"]
    else:
        paths = sorted(Path("runs").glob("*/duplicate_groups.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in paths:  # Search the first matching group in candidate-file order.
        if not path.exists():  # Some runs may not have produced a duplicate-group file yet.
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:  # Each line in duplicate_groups.jsonl represents one duplicate cluster.
                if not line.strip():  # Tolerate blank lines left after manual editing.
                    continue
                group = json.loads(line)
                if group.get("group_id") == group_id:  # Return immediately when the record is found in the newest or specified run.
                    group["run_dir"] = str(path.parent)
                    return group
    return None


def _find_item_in_run_outputs(item_id: str, run_dir: Path) -> dict | None:
    """Find an item inside run output sample files.

    Business logic:
        1. Check kept, removed, and review output files in sequence.
        2. Reuse the JSONL lookup logic to match item_id.
        3. Add output_file to the matched sample so its source is visible.

    Args:
        item_id (str): Sample id to find.
        run_dir (Path): Workflow-run output directory.

    Returns:
        dict | None: Matched sample, or None when not found.

    Examples:
        >>> _find_item_in_run_outputs("missing", Path("missing-run")) is None
        True
    """
    for name in ("kept.jsonl", "removed.jsonl", "review.jsonl"):  # The three action output files cover the full final sample set.
        path = run_dir / name
        item = _find_item_in_jsonl(item_id, path)
        if item:  # Mark the source file so the user can see the final sample action.
            item["output_file"] = name
            return item
    return None


def _find_item_in_jsonl(item_id: str, path: Path) -> dict | None:
    """Find a record by item id inside a JSONL file.

    Business logic:
        1. Return None when the file does not exist.
        2. Parse the JSONL file line by line.
        3. Compare stringified ids and return the full record on a match.

    Args:
        item_id (str): Sample id to match.
        path (Path): JSONL file path.

    Returns:
        dict | None: Matched sample, or None when not found.

    Examples:
        >>> _find_item_in_jsonl("missing", Path("missing.jsonl")) is None
        True
    """
    if not path.exists():  # Inspect commands allow missing input or output files.
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:  # Each JSONL line corresponds to one sample record.
            if not line.strip():  # Blank lines do not participate in item matching.
                continue
            item = json.loads(line)
            if str(item.get("id")) == item_id:  # Compare ids as strings to support numeric ids too.
                return item
    return None


def _find_groups_for_item(item_id: str, run_dir: Path) -> list[dict]:
    """Find duplicate groups containing the specified item.

    Business logic:
        1. Locate duplicate_groups.jsonl under run_dir.
        2. Return an empty list when the file does not exist.
        3. Collect all groups whose member_ids contain the target item_id.

    Args:
        item_id (str): Sample id whose related groups should be found.
        run_dir (Path): Workflow-run output directory.

    Returns:
        list[dict]: Duplicate groups containing the sample.

    Examples:
        >>> _find_groups_for_item("missing", Path("missing-run"))
        []
    """
    path = run_dir / "duplicate_groups.jsonl"
    groups = []
    if not path.exists():  # No duplicate-group output means this run produced no inspectable groups.
        return groups
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:  # Scan one group at a time so one item can appear in multiple groups.
            if not line.strip():  # Skip blank lines to tolerate manually edited files.
                continue
            group = json.loads(line)
            if item_id in [str(member_id) for member_id in group.get("member_ids", [])]:  # Compare member ids as strings consistently.
                groups.append(group)
    return groups


def build_parser() -> argparse.ArgumentParser:
    """Build the dedup command-line argument parser.

    Business logic:
        1. Create the top-level argparse parser.
        2. Register run, auto-run, validate, inspect-group, and inspect-item subcommands.
        3. Bind each subcommand to its handler function.

    Args:
        None: Parser construction does not require external arguments.

    Returns:
        argparse.ArgumentParser: Full dedup command-line parser.

    Examples:
        >>> build_parser().prog
        'dedup'
    """
    parser = argparse.ArgumentParser(prog="dedup", description="Run deduplication workflows.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a dedup workflow.")
    run_parser.add_argument("-c", "--config", required=True, help="Path to workflow config.")
    run_parser.add_argument("--resume", action="store_true", help="Resume from checkpoint and existing outputs.")
    run_parser.set_defaults(func=run_command)

    auto_run_parser = subparsers.add_parser("auto-run", help="Route input by modality and run the matching workflow.")
    auto_run_parser.add_argument("--input", required=True, help="Input JSONL path.")
    auto_run_parser.add_argument("--output-dir", required=True, help="Output directory for routed runs.")
    auto_run_parser.add_argument("--workflow-dir", default="workflows", help="Directory containing workflow templates.")
    auto_run_parser.add_argument("--profile", choices=["strict", "basic"], default="strict", help="Workflow profile.")
    auto_run_parser.add_argument("--modality", choices=["auto", "text", "image", "audio"], default="auto", help="Force one modality.")
    auto_run_parser.add_argument("--resume", action="store_true", help="Resume routed workflows from checkpoints.")
    auto_run_parser.set_defaults(func=auto_run_command)

    validate_parser = subparsers.add_parser("validate", help="Validate a workflow config.")
    validate_parser.add_argument("-c", "--config", required=True, help="Path to workflow config.")
    validate_parser.set_defaults(func=validate_command)

    template_parser = subparsers.add_parser("operator-template", help="Generate a custom end-to-end operator template.")
    template_parser.add_argument("--type", required=True, choices=["text", "image", "audio"], help="End-to-end operator template type.")
    template_parser.add_argument("--name", required=True, help="snake_case operator_name used in workflow steps.")
    template_parser.add_argument("--output", required=True, help="Output Python file path.")
    template_parser.set_defaults(func=operator_template_command)

    inspect_parser = subparsers.add_parser("inspect-group", help="Inspect a duplicate group.")
    inspect_parser.add_argument("--group-id", required=True, help="Duplicate group id.")
    inspect_parser.add_argument("--run-dir", help="Run directory. If omitted, all runs are searched newest first.")
    inspect_parser.set_defaults(func=inspect_group_command)

    inspect_item_parser = subparsers.add_parser("inspect-item", help="Inspect an input/output item by id.")
    inspect_item_parser.add_argument("--item-id", required=True, help="Sample id.")
    inspect_item_parser.add_argument("--run-dir", required=True, help="Run directory.")
    inspect_item_parser.add_argument("--input", help="Input JSONL path.")
    inspect_item_parser.add_argument("--max-text-chars", type=int, default=300, help="Maximum displayed text length.")
    inspect_item_parser.add_argument("--verbose", action="store_true", help="Print full input/output records.")
    inspect_item_parser.set_defaults(func=inspect_item_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the main dedup command-line entrypoint.

    Business logic:
        1. Load local env files from the current directory first.
        2. Build the parser and parse argv.
        3. Execute the subcommand function and convert ValueError into a user-readable command-line error.

    Args:
        argv (list[str] | None, optional): command-line argument list; None means to use sys.argv.

    Returns:
        int: Process exit code.

    Examples:
        >>> main(["validate", "-c", "workflow.yaml"])  # doctest: +SKIP
        0
    """
    load_local_env_files(Path.cwd())
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:  # Config and input errors should surface as concise command-line errors.
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
