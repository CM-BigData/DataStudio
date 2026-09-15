from __future__ import annotations

import copy
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from dedup_workflow_engine.operators.base import BaseOperator
from dedup_workflow_engine.runtime.checkpoint import CheckpointManager
from dedup_workflow_engine.runtime.dag import WorkflowStep, build_execution_plan, flatten_plan
from dedup_workflow_engine.runtime.input_adapter import InputAdapter
from dedup_workflow_engine.runtime.loader import resolve_path
from dedup_workflow_engine.runtime.metrics import action_count, issue_distribution
from dedup_workflow_engine.runtime.registry import OperatorRegistry
from dedup_workflow_engine.runtime.report import write_report
from dedup_workflow_engine.runtime.scheduler import load_runtime_config


PROCESS_EXECUTORS = {"process", "multiprocess", "process_pool"}  # Workflow config: runtime executor names allowed to use ProcessPoolExecutor for DAG levels.


def _safe_run_child_path(run_dir: Path, value: Any, name: str) -> Path:
    """Resolve a configured output file below the workflow run directory."""
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if "\x00" in text or any(ord(char) < 32 for char in text):
        raise ValueError(f"{name} contains unsupported control characters")
    child = Path(text)
    if child.is_absolute() or ".." in child.parts:
        raise ValueError(f"{name} must stay under the workflow run directory")
    return run_dir / child


class WorkflowExecutor:
    def __init__(self, config: dict[str, Any], registry: OperatorRegistry) -> None:
        """Create an executor for one workflow config.

        Business logic:
            1. Store the full workflow config.
            2. Store the operator registry so operators can be created by step.
            3. Pin the current working directory as the base for resolving relative paths.

        Args:
            config (dict[str, Any]): Config containing workflow, input, output, runtime, and steps.
            registry (OperatorRegistry): Registry used to create workflow-step operators.

        Returns:
            None: This initializer does not return a value.

        Examples:
            >>> WorkflowExecutor({"workflow": {}, "input": {}, "output": {}, "steps": []}, OperatorRegistry())  # doctest: +SKIP
        """
        self.config = config  # Workflow config: full workflow config used by the current run.
        self.registry = registry  # Workflow config: creates operator instances by workflow-step operator name.
        self.cwd = Path.cwd()  # Workflow config: execution base directory for resolving relative input/output paths.

    def run(self) -> dict[str, Any]:
        """Run the configured deduplication workflow and write artifacts.

        Business logic:
            1. Resolve input, output, runtime, checkpoint, and execution plan settings.
            2. Execute operators by pipeline step or DAG level while maintaining shared context.
            3. Write sample outputs, metrics, and the Markdown report.

        Args:
            None: The executor uses the config and registry passed during initialization.

        Returns:
            dict[str, Any]: Run-summary metrics, including report_path.

        Raises:
            ValueError: Raised when the input path points to a ground-truth file.
            RuntimeError: Raised when a parallel step fails.

        Examples:
            >>> WorkflowExecutor(config={}, registry=OperatorRegistry()).run()  # doctest: +SKIP
            {'workflow_id': 'demo'}
        """
        workflow = self.config["workflow"]
        input_config = self.config["input"]
        output_config = self.config["output"]
        run_dir = resolve_path(output_config["run_dir"], self.cwd)
        run_dir.mkdir(parents=True, exist_ok=True)
        input_path = resolve_path(input_config["path"], self.cwd) if input_config.get("path") else None
        if input_path and "ground_truth" in str(input_path).lower():  # Guard against accidentally deduplicating evaluation labels.
            raise ValueError(f"workflow input must not point to ground truth: {input_path}")

        runtime = load_runtime_config(self.config)
        checkpoint = CheckpointManager(run_dir, enabled=runtime.checkpoint)
        plan = build_execution_plan(self.config["steps"], mode=str(workflow.get("mode", "pipeline")))
        ordered_steps = flatten_plan(plan)
        context: dict[str, Any] = {
            "cwd": str(self.cwd),
            "workflow_id": workflow.get("id", "unknown"),
            "modality": workflow.get("modality", "unknown"),
            "runtime": runtime.__dict__,
            "duplicate_edges": [],
            "duplicate_groups": [],
            "operator_logs": [],
        }

        input_adapter = InputAdapter(input_config, base_dir=self.cwd)
        items = [self._prepare_item(item) for item in input_adapter.read()]
        start_after_index = -1
        skipped_step_count = 0
        if runtime.resume:  # Restore the latest successful step state before executing remaining steps.
            latest_state = checkpoint.latest_successful_state([step.id for step in ordered_steps])
            if latest_state:  # Resume is best-effort; fresh runs continue when no checkpoint is present.
                start_after_index, state = latest_state
                skipped_step_count = start_after_index + 1
                items = state["items"]
                context.update(state.get("context", {}))
                context["runtime"] = runtime.__dict__

        step_position = {step.id: index for index, step in enumerate(ordered_steps)}

        started = time.time()
        operator_log_path = _safe_run_child_path(run_dir, output_config.get("operator_log_path", "operator_logs.jsonl"), "operator_log_path")
        log_mode = "a" if runtime.resume and operator_log_path.exists() else "w"
        with operator_log_path.open(log_mode, encoding="utf-8") as operator_log:
            for level in plan:  # Execute each pipeline step or DAG level in dependency order.
                runnable_level = [step for step in level if step_position[step.id] > start_after_index]
                if not runnable_level:  # Entire levels before the resume point are already persisted.
                    continue
                if self._can_run_level_in_parallel(runnable_level, runtime):  # Only independent safe steps use processes.
                    items = self._run_parallel_level(runnable_level, items, context, checkpoint, operator_log, runtime.workers)
                    continue
                for step in runnable_level:  # Sequential execution preserves operator side effects in shared context.
                    if step_position[step.id] <= start_after_index:  # Extra guard for resumed DAG levels.
                        continue
                    operator = self.registry.create(step.operator, config=step.params)
                    operator.setup()
                    items = self._run_step(step, operator, items, context, checkpoint, operator_log)

        self._default_actions(items)
        groups = context.get("duplicate_groups", [])
        self._write_outputs(run_dir, output_config, items, groups)

        elapsed = round(time.time() - started, 3)
        stats = {
            "workflow_id": workflow.get("id", "unknown"),
            "modality": workflow.get("modality", "unknown"),
            "total_count": len(items),
            "kept_count": action_count(items, "keep"),
            "removed_count": action_count(items, "remove"),
            "review_count": action_count(items, "review"),
            "duplicate_group_count": len(groups),
            "duplicate_edge_count": len(context.get("duplicate_edges", [])),
            "execution_mode": workflow.get("mode", "pipeline"),
            "runtime": runtime.__dict__,
            "resume_enabled": runtime.resume,
            "resume_count": 1 if runtime.resume else 0,
            "skipped_count": skipped_step_count,
            "processed_count": len(items),
            "completed_count": len(items),
            "completed_ids": [str(item.get("id")) for item in items if item.get("id")],
            "failed_count": action_count(items, "review"),
            "issue_distribution": issue_distribution(items),
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started)),
            "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "elapsed_seconds": elapsed,
            "throughput_qps": round(len(items) / elapsed, 3) if elapsed > 0 else len(items),
        }
        metrics_path = _safe_run_child_path(run_dir, output_config.get("metrics_path", "metrics.json"), "metrics_path")
        metrics_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path = _safe_run_child_path(run_dir, output_config.get("report_path", "report.md"), "report_path")
        write_report(report_path, stats, groups)
        stats["report_path"] = str(report_path)
        return stats

    def _build_operators(self, steps: list[WorkflowStep], start_after_index: int = -1) -> dict[str, BaseOperator]:
        """Create workflow operator instances that still need to run.

        Business logic:
            1. Iterate over the flattened workflow steps.
            2. Skip steps before the resume-completed position.
            3. Create and set up each remaining operator from the registry.

        Args:
            steps (list[WorkflowStep]): Workflow steps in execution order.
            start_after_index (int, optional): Index of the last step already completed by resume. Defaults to -1.

        Returns:
            dict[str, BaseOperator]: Operator instances keyed by step id.

        Examples:
            >>> WorkflowExecutor({}, OperatorRegistry())._build_operators([], -1)
            {}
        """
        operators: dict[str, BaseOperator] = {}
        for index, step in enumerate(steps):  # Skip already-completed operators when resuming.
            if index <= start_after_index:  # Steps already completed by resume do not need new operators.
                continue
            operator = self.registry.create(step.operator, config=step.params)
            operator.setup()
            operators[step.id] = operator
        return operators

    def _can_run_level_in_parallel(self, level: list[WorkflowStep], runtime: Any) -> bool:
        """Determine whether a DAG level can run in process-based parallel mode.

        Business logic:
            1. Do not enable parallelism for a single-step level.
            2. Require runtime to explicitly allow it and provide at least 2 workers.
            3. Require both the executor name and each step's parallel_safe flag to allow it.

        Args:
            level (list[WorkflowStep]): Workflow steps in the same dependency level.
            runtime (Any): RuntimeConfig or a compatible object.

        Returns:
            bool: True when the level satisfies process-parallel conditions.

        Examples:
            >>> WorkflowExecutor({}, OperatorRegistry())._can_run_level_in_parallel([], object())
            False
        """
        if len(level) < 2:  # One step has no parallelism benefit.
            return False
        if not runtime.allow_parallel_steps or runtime.workers < 2:  # Parallel execution must be explicitly enabled.
            return False
        if str(runtime.executor).lower() not in PROCESS_EXECUTORS:  # Local executor keeps all work in the main process.
            return False
        return all(bool(step.raw.get("parallel_safe", True)) for step in level)

    def _run_parallel_level(
        self,
        level: list[WorkflowStep],
        items: list[dict[str, Any]],
        context: dict[str, Any],
        checkpoint: CheckpointManager,
        operator_log: Any,
        workers: int,
    ) -> list[dict[str, Any]]:
        """Run independent DAG steps in worker processes and merge results.

        Business logic:
            1. Deep-copy items and context for each parallel step to isolate branch side effects.
            2. Collect all worker results and merge them in workflow order.
            3. Record operator logs, checkpoints, and resumable runtime state.

        Args:
            level (list[WorkflowStep]): Steps in the level that should run in parallel.
            items (list[dict[str, Any]]): Sample list before entering this level.
            context (dict[str, Any]): Shared workflow context before entering this level.
            checkpoint (CheckpointManager): Checkpoint manager for the current run.
            operator_log (Any): Open JSONL file handle for operator logs.
            workers (int): Maximum worker process count.

        Returns:
            list[dict[str, Any]]: Sample list after merging all successful branches.

        Raises:
            RuntimeError: Raised when any parallel step fails.

        Examples:
            >>> WorkflowExecutor({}, OperatorRegistry())._run_parallel_level([], [], {}, CheckpointManager(Path("."), False), None, 1)  # doctest: +SKIP
            []
        """
        base_items = copy.deepcopy(items)
        base_context = copy.deepcopy(context)
        tasks = []
        with ProcessPoolExecutor(max_workers=min(workers, len(level))) as pool:
            future_to_step = {}
            for step in level:  # Each branch receives isolated copies so operators cannot mutate shared memory.
                payload = {
                    "id": step.id,
                    "operator": step.operator,
                    "params": step.params,
                }
                future = pool.submit(_run_operator_in_process, payload, copy.deepcopy(base_items), copy.deepcopy(base_context))
                future_to_step[future] = step
            for future in as_completed(future_to_step):  # Collect all branch results before deterministic merging.
                result = future.result()
                tasks.append(result)

        by_step = {result["step_id"]: result for result in tasks}
        merged_items = copy.deepcopy(base_items)
        merged_context = context
        for step in level:  # Merge in workflow order so output does not depend on process completion order.
            result = by_step[step.id]
            if result["status"] != "success":  # Failed branches are logged and checkpointed before aborting the level.
                log_entry = result["log_entry"]
                merged_context["operator_logs"].append(log_entry)
                operator_log.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                checkpoint.write_step(
                    step.id,
                    str(result["operator_name"]),
                    {
                        "status": result["status"],
                        "processed_count": len(result["items"]),
                        "duplicate_edge_count": len(merged_context.get("duplicate_edges", [])),
                        "duplicate_group_count": len(merged_context.get("duplicate_groups", [])),
                        "parallel": True,
                    },
                )
                raise RuntimeError(f"parallel workflow step failed: {step.id}: {result.get('error', '')}")
            merged_items = _merge_parallel_items(merged_items, result["items"])
            merged_context.setdefault("duplicate_edges", []).extend(result.get("duplicate_edges_delta", []))
            merged_context.setdefault("duplicate_groups", []).extend(result.get("duplicate_groups_delta", []))
            log_entry = result["log_entry"]
            merged_context["operator_logs"].append(log_entry)
            operator_log.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
            checkpoint.write_step(
                step.id,
                str(result["operator_name"]),
                {
                    "status": result["status"],
                    "processed_count": len(result["items"]),
                    "duplicate_edge_count": len(merged_context.get("duplicate_edges", [])),
                    "duplicate_group_count": len(merged_context.get("duplicate_groups", [])),
                    "parallel": True,
                },
            )

        for step in level:  # Store the merged state under each completed parallel step for resume.
            checkpoint.write_runtime_state(step.id, merged_items, merged_context)
        return merged_items

    def _run_step(
        self,
        step: WorkflowStep,
        operator: BaseOperator,
        items: list[dict[str, Any]],
        context: dict[str, Any],
        checkpoint: CheckpointManager,
        operator_log: Any,
    ) -> list[dict[str, Any]]:
        """Run one workflow step and record audit information.

        Business logic:
            1. Call the operator's process_dataset to process samples.
            2. When it fails, mark input samples with operator_failed and review.
            3. Whether successful or failed, tear down the operator and write logs and checkpoints.

        Args:
            step (WorkflowStep): Workflow step currently being executed.
            operator (BaseOperator): Operator instance for the current step.
            items (list[dict[str, Any]]): Sample list entering the step.
            context (dict[str, Any]): Shared workflow context.
            checkpoint (CheckpointManager): Checkpoint manager for the current run.
            operator_log (Any): Open JSONL file handle for operator logs.

        Returns:
            list[dict[str, Any]]: Sample list returned by the operator.

        Examples:
            >>> WorkflowExecutor({}, OperatorRegistry())._run_step  # doctest: +ELLIPSIS
            <bound method...
        """
        before = time.time()
        status = "success"
        error = None
        processed_items = items
        try:
            processed_items = operator.process_dataset(items, context)
            return processed_items
        except Exception as exc:
            status = "failed"
            error = str(exc)
            for item in items:  # All input samples need manual review when the operator fails.
                item.setdefault("issues", []).append("operator_failed")
                item["action"] = "review"
            raise
        finally:
            try:
                operator.teardown()
            finally:
                log_entry = {
                    "step_id": step.id,
                    "operator": operator.operator_name,
                    "status": status,
                    "latency_ms": round((time.time() - before) * 1000, 3),
                    "input_count": len(items),
                    "duplicate_edge_count": len(context.get("duplicate_edges", [])),
                    "duplicate_group_count": len(context.get("duplicate_groups", [])),
                }
                if error:  # Include operator failure text in the audit log without swallowing the exception.
                    log_entry["error"] = error
                context["operator_logs"].append(log_entry)
                operator_log.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
                checkpoint.write_step(
                    step.id,
                    operator.operator_name,
                    {
                        "status": status,
                        "processed_count": len(items),
                        "duplicate_edge_count": len(context.get("duplicate_edges", [])),
                        "duplicate_group_count": len(context.get("duplicate_groups", [])),
                    },
                )
                if status == "success":  # Only successful outputs are safe resume points.
                    checkpoint.write_runtime_state(step.id, processed_items, context)

    def _read_jsonl(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSONL input line by line and preserve invalid lines.

        Business logic:
            1. Read with utf-8-sig to support BOM-prefixed files.
            2. Skip blank lines and parse JSON line by line.
            3. When JSON parsing fails, emit a review sample instead of aborting the whole batch.

        Args:
            path (Path): Input JSONL file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of parsed sample records.

        Examples:
            >>> list(WorkflowExecutor({}, OperatorRegistry())._read_jsonl(Path("input.jsonl")))  # doctest: +SKIP
            [{'id': 'sample'}]
        """
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_no, line in enumerate(handle, start=1):  # Track line numbers for synthetic invalid-record ids.
                line = line.strip()
                if not line:  # Empty JSONL lines are ignored.
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    yield {
                        "id": f"invalid_json_line_{line_no}",
                        "modality": "unknown",
                        "payload": {"raw": line},
                        "issues": ["invalid_json"],
                        "action": "review",
                        "error": str(exc),
                    }

    def _prepare_item(self, item: dict[str, Any]) -> dict[str, Any]:
        """Fill in default sample fields required by operators.

        Business logic:
            1. Generate a unique id for samples missing one.
            2. Fill the default modality from workflow config.
            3. Initialize payload, meta, intermediate, metrics, issues, and action.

        Args:
            item (dict[str, Any]): Raw or partially normalized sample record.

        Returns:
            dict[str, Any]: The same sample record with default fields filled in.

        Examples:
            >>> item = WorkflowExecutor({"workflow": {"modality": "text"}}, OperatorRegistry())._prepare_item({})
            >>> item["modality"]
            'text'
        """
        item.setdefault("id", f"sample_{time.time_ns()}")
        item.setdefault("modality", self.config.get("workflow", {}).get("modality", "unknown"))
        item.setdefault("payload", {})
        item.setdefault("meta", {})
        item.setdefault("intermediate", {})
        item.setdefault("metrics", {})
        item.setdefault("issues", [])
        item.setdefault("action", "pending")
        return item

    def _default_actions(self, items: list[dict[str, Any]]) -> None:
        """Default undecided samples to kept samples.

        Business logic:
            1. Iterate over all final samples.
            2. Find samples whose action is still pending.
            3. Change their action to keep, meaning they did not hit any duplicate-removal rule.

        Args:
            items (list[dict[str, Any]]): Final sample list after all operators have run.

        Returns:
            None: Sample actions are modified in place and nothing is returned.

        Examples:
            >>> rows = [{"action": "pending"}]
            >>> WorkflowExecutor({}, OperatorRegistry())._default_actions(rows)
            >>> rows[0]["action"]
            'keep'
        """
        for item in items:  # Operators only need to mark removals or reviews; untouched samples are kept.
            if item.get("action") == "pending":  # Only samples untouched by any operator decision default to keep.
                item["action"] = "keep"

    def _write_outputs(
        self,
        run_dir: Path,
        output_config: dict[str, Any],
        items: list[dict[str, Any]],
        groups: list[dict[str, Any]],
    ) -> None:
        """Write final sample outputs and duplicate-group JSONL artifacts.

        Business logic:
            1. Resolve kept, removed, review, and duplicate_groups filenames from output_config.
            2. Split samples by action and write them into the matching JSONL files.
            3. Write duplicate groups line by line into a separate JSONL file.

        Args:
            run_dir (Path): Output directory for the current run.
            output_config (dict[str, Any]): Workflow output config.
            items (list[dict[str, Any]]): Final sample list with action decisions.
            groups (list[dict[str, Any]]): Duplicate-group list produced by the current run.

        Returns:
            None: Output files are written to disk and nothing is returned.

        Examples:
            >>> WorkflowExecutor({}, OperatorRegistry())._write_outputs(Path("."), {}, [], [])  # doctest: +SKIP
        """
        kept_path = _safe_run_child_path(run_dir, output_config.get("kept_path", "kept.jsonl"), "kept_path")
        removed_path = _safe_run_child_path(run_dir, output_config.get("removed_path", "removed.jsonl"), "removed_path")
        review_path = _safe_run_child_path(run_dir, output_config.get("review_path", "review.jsonl"), "review_path")
        groups_path = _safe_run_child_path(run_dir, output_config.get("duplicate_groups_path", "duplicate_groups.jsonl"), "duplicate_groups_path")

        with kept_path.open("w", encoding="utf-8") as kept, removed_path.open("w", encoding="utf-8") as removed, review_path.open(
            "w", encoding="utf-8"
        ) as review:
            for item in items:  # Split sample records into the action-specific files expected by deliverables.
                line = json.dumps(item, ensure_ascii=False) + "\n"
                if item.get("action") == "remove":  # Removed samples have a selected representative elsewhere.
                    removed.write(line)
                elif item.get("action") == "review":  # Review samples need human or downstream adjudication.
                    review.write(line)
                else:
                    kept.write(line)

        with groups_path.open("w", encoding="utf-8") as handle:
            for group in groups:  # Full duplicate group details are stored separately from item action files.
                handle.write(json.dumps(group, ensure_ascii=False) + "\n")


def _run_operator_in_process(step: dict[str, Any], items: list[dict[str, Any]], context: dict[str, Any]) -> dict[str, Any]:
    """Run one operator inside a worker process.

    Business logic:
        1. Rebuild the default operator registry inside the child process.
        2. Execute the specified step's operator and capture new duplicate edges and groups.
        3. Return mergeable items, context delta, and log entry to the main process.

    Args:
        step (dict[str, Any]): Serializable workflow-step payload.
        items (list[dict[str, Any]]): Branch-private copy of the sample list.
        context (dict[str, Any]): Branch-private copy of workflow context.

    Returns:
        dict[str, Any]: Step result containing processed items, context delta, and log entry.

    Examples:
        >>> _run_operator_in_process({"id": "x", "operator": "Missing"}, [], {})  # doctest: +SKIP
        {'status': 'failed'}
    """
    from dedup_workflow_engine.runtime.registry import build_default_registry

    before = time.time()
    status = "success"
    error = None
    processed_items = items
    initial_edge_count = len(context.get("duplicate_edges", []))
    initial_group_count = len(context.get("duplicate_groups", []))
    registry = build_default_registry()
    operator = registry.create(str(step["operator"]), config=dict(step.get("params", {})))
    operator.setup()
    try:
        processed_items = operator.process_dataset(items, context)
    except Exception as exc:  # pragma: no cover - exercised by integration failure paths
        status = "failed"
        error = str(exc)
        for item in items:  # Failed parallel branches mark all branch items for review before returning.
            item.setdefault("issues", []).append("operator_failed")
            item["action"] = "review"
        processed_items = items
    finally:
        operator.teardown()

    log_entry = {
        "step_id": step["id"],
        "operator": operator.operator_name,
        "status": status,
        "latency_ms": round((time.time() - before) * 1000, 3),
        "input_count": len(items),
        "duplicate_edge_count": len(context.get("duplicate_edges", [])),
        "duplicate_group_count": len(context.get("duplicate_groups", [])),
        "parallel": True,
    }
    if error:  # Keep worker errors visible in the main-process operator log.
        log_entry["error"] = error
    return {
        "step_id": step["id"],
        "operator_name": operator.operator_name,
        "status": status,
        "error": error,
        "items": processed_items,
        "duplicate_edges_delta": context.get("duplicate_edges", [])[initial_edge_count:],
        "duplicate_groups_delta": context.get("duplicate_groups", [])[initial_group_count:],
        "log_entry": log_entry,
    }


def _merge_parallel_items(base_items: list[dict[str, Any]], branch_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge one parallel branch's sample updates back into the base sample list.

    Business logic:
        1. Build an index of branch items by item id.
        2. Merge samples one by one in the original base_items order.
        3. Keep the base version when a sample is missing from the branch.

    Args:
        base_items (list[dict[str, Any]]): Base sample list before the parallel level.
        branch_items (list[dict[str, Any]]): Sample list returned by one worker branch.

    Returns:
        list[dict[str, Any]]: Sample list with branch updates merged in.

    Examples:
        >>> _merge_parallel_items([{"id": "1"}], [{"id": "1", "action": "keep"}])[0]["action"]
        'keep'
    """
    by_id = {str(item.get("id")): item for item in branch_items}
    merged = []
    for item in base_items:  # Preserve base order even when branch output order differs.
        item_id = str(item.get("id"))
        branch = by_id.get(item_id)
        if not branch:  # Missing branch output leaves the original item untouched.
            merged.append(item)
            continue
        merged.append(_merge_item(item, branch))
    return merged


def _merge_item(base: dict[str, Any], branch: dict[str, Any]) -> dict[str, Any]:
    """Merge one parallel-branch sample into the base sample.

    Business logic:
        1. Deep-copy the base sample to avoid mutating the input object.
        2. Merge payload, meta, intermediate, metrics, and issues.
        3. Merge action by priority and keep branch-only top-level fields.

    Args:
        base (dict[str, Any]): Base sample before parallel-branch execution.
        branch (dict[str, Any]): Sample returned by the branch operator.

    Returns:
        dict[str, Any]: Merged sample record.

    Examples:
        >>> _merge_item({"id": "1", "issues": []}, {"id": "1", "issues": ["x"]})["issues"]
        ['x']
    """
    output = copy.deepcopy(base)
    for key in ("payload", "meta", "intermediate", "metrics"):  # Merge nested operator fields instead of replacing the whole item.
        if isinstance(branch.get(key), dict):  # Merge only dict-shaped nested fields to avoid corrupting base structure with unexpected types.
            output.setdefault(key, {}).update(branch[key])
    if isinstance(branch.get("issues"), list):  # Preserve unique issue labels from both branches.
        issues = output.setdefault("issues", [])
        for issue in branch["issues"]:  # Newly added branch issues must be appended without duplication.
            if issue not in issues:  # Existing issues are not written twice.
                issues.append(issue)
    output["action"] = _merge_action(str(output.get("action", "pending")), str(branch.get("action", "pending")))
    for key, value in branch.items():  # Copy branch-only top-level fields such as debug outputs.
        if key not in output:  # Keep branch fields missing from the base sample as supplemental information.
            output[key] = value
    return output


def _merge_action(left: str, right: str) -> str:
    """Merge actions from two parallel branches for one sample.

    Business logic:
        1. Define priorities for pending, keep, remove, and review.
        2. Compare the priorities of the two actions.
        3. Return the higher-priority action so review is never overwritten.

    Args:
        left (str): Action already present on the base sample.
        right (str): Action returned by the branch sample.

    Returns:
        str: Higher-priority action.

    Examples:
        >>> _merge_action("keep", "review")
        'review'
    """
    priority = {"pending": 0, "keep": 1, "remove": 2, "review": 3}
    return left if priority.get(left, 0) >= priority.get(right, 0) else right
