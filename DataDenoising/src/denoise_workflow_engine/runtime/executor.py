from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Iterable, Sequence

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.runtime.input_adapter import InputAdapter
from denoise_workflow_engine.runtime.loader import resolve_path
from denoise_workflow_engine.runtime.registry import OperatorRegistry
from denoise_workflow_engine.runtime.report import write_report


class WorkflowExecutor:
    def __init__(
        self,
        config: dict[str, Any],
        registry: OperatorRegistry,
        base_dir: Path | None = None,
        allowed_roots: Sequence[Path] | None = None,
    ) -> None:
        """Store workflow configuration and execution dependencies.

        Business logic:
            1. Accept configuration and dependency objects from the caller.
            2. Store reusable state needed during workflow execution.
            3. Avoid expensive external calls during object construction.

        Args:
                config (dict[str, Any]): Workflow configuration dictionary.
                registry (OperatorRegistry): Operator registry.
                base_dir (Path | None): Base directory for resolving workflow-relative paths.

        Returns:
            None: The constructor initializes the executor in place.

        Examples:
            >>> callable(WorkflowExecutor)
            True
        """
        self.config = config  # Runtime configuration such as thresholds, paths, and API parameters.
        self.registry = registry  # Operator registry used to instantiate workflow steps by name.
        self.cwd = base_dir or Path.cwd()  # Base directory for resolving relative workflow input and output paths.
        self.allowed_roots = tuple(allowed_roots) if allowed_roots is not None else None

    def run(self) -> dict[str, Any]:
        """Execute the complete denoising workflow.

        Business logic:
            1. Read workflow, input, output, and step configuration.
            2. Execute operators step by step and write keep/drop/review JSONL outputs.
            3. Generate operator logs, metrics, checkpoint data, and the final report.

        Args:
                None: This method does not take input parameters.

        Returns:
            dict[str, Any]: Workflow execution statistics.

        Examples:
            >>> run
            run
        """
        workflow = self.config["workflow"]
        input_config = self.config["input"]
        output_config = self.config["output"]

        run_dir = resolve_path(
            output_config["run_dir"],
            self.cwd,
            allowed_roots=self.allowed_roots,
            name="run directory",
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        operators = self._build_operators(self._ordered_steps(self.config["steps"]), run_dir)
        checkpoint_path = resolve_path(
            "checkpoint.json",
            run_dir,
            allowed_roots=(run_dir,),
            name="checkpoint path",
        )
        operator_log_path = resolve_path(
            "operator_logs.jsonl",
            run_dir,
            allowed_roots=(run_dir,),
            name="operator log path",
        )
        metrics_path = resolve_path(
            "metrics.json",
            run_dir,
            allowed_roots=(run_dir,),
            name="metrics path",
        )
        resume_enabled = bool(workflow.get("resume", False))
        checkpoint_enabled = bool(workflow.get("checkpoint", False) or resume_enabled)
        completed_ids = self._load_checkpoint(checkpoint_path) if resume_enabled else set()
        output_mode = "a" if resume_enabled and completed_ids else "w"

        run_output_paths = {
            "keep": resolve_path(
                output_config.get("clean_path", "clean.jsonl"),
                run_dir,
                allowed_roots=(run_dir,),
                name="output.clean_path",
            ),
            "drop": resolve_path(
                output_config.get("dropped_path", "dropped.jsonl"),
                run_dir,
                allowed_roots=(run_dir,),
                name="output.dropped_path",
            ),
            "review": resolve_path(
                output_config.get("review_path", "review.jsonl"),
                run_dir,
                allowed_roots=(run_dir,),
                name="output.review_path",
            ),
            "report": resolve_path(
                output_config.get("report_path", "report.md"),
                run_dir,
                allowed_roots=(run_dir,),
                name="output.report_path",
            ),
        }
        outputs = {
            action: run_output_paths[action].open(output_mode, encoding="utf-8")
            for action in ("keep", "drop", "review")
        }
        operator_log = operator_log_path.open(output_mode, encoding="utf-8")

        stats = {
            "workflow_id": workflow.get("id", "unknown"),
            "total_count": 0,
            "current_run_count": 0,
            "input_total_count": 0,
            "historical_completed_count": 0,
            "newly_processed_count": 0,
            "current_completed_count": len(completed_ids),
            "pending_count": 0,
            "keep_count": 0,
            "drop_count": 0,
            "review_count": 0,
            "failed_count": 0,
            "issue_distribution": {},
            "started_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "resume_enabled": resume_enabled,
            "resume_count": 1 if resume_enabled else 0,
            "skipped_count": 0,
            "processed_count": 0,
            "concurrency": max(1, int(workflow.get("concurrency", 1))),
            "concurrency_enabled": False,
            "parallelized_count": 0,
            "serial_step_count": 0,
        }

        started = time.time()
        try:
            items: list[dict[str, Any]] = []
            input_total_count = 0
            input_reader = InputAdapter(input_config, self.cwd, allowed_roots=self.allowed_roots)
            for item in input_reader.read():  # The input adapter normalizes flexible user input into DataItem records.
                input_total_count += 1
                processed = self._prepare_item(item)
                if resume_enabled and processed["id"] in completed_ids:  # Skip samples already completed during resume runs.
                    stats["skipped_count"] += 1
                    continue
                stats["current_run_count"] += 1
                stats["processed_count"] += 1
                items.append(processed)
            stats["total_count"] = input_total_count
            stats["input_total_count"] = input_total_count
            stats["historical_completed_count"] = stats["skipped_count"]
            stats["newly_processed_count"] = len(items)
            stats["pending_count"] = len(items)

            for operator in operators:  # Execute operators in workflow order, with per-item concurrency inside each operator.
                items = self._run_operator_on_items(operator, items, stats)

            for processed in items:  # Write outputs, issue distribution, and checkpoint data on the main thread.
                for trace in processed.get("operator_trace", []):  # Centralize operator log writes to avoid concurrent file writes.
                    operator_log.write(json.dumps(trace, ensure_ascii=False) + "\n")
                action = processed.get("action") or "keep"
                if action not in outputs:  # Route unknown actions to manual review.
                    action = "review"
                    processed["action"] = action
                outputs[action].write(json.dumps(processed, ensure_ascii=False) + "\n")
                stats[f"{action}_count"] += 1
                for issue in processed.get("issues", []):  # Accumulate issue tag distribution across all samples.
                    stats["issue_distribution"][issue] = stats["issue_distribution"].get(issue, 0) + 1
                if checkpoint_enabled:  # Persist sample progress when checkpointing is enabled.
                    completed_ids.add(str(processed["id"]))
                    stats["current_completed_count"] = len(completed_ids)
                    stats["pending_count"] = max(0, stats["input_total_count"] - stats["current_completed_count"])
                    self._write_checkpoint(checkpoint_path, workflow.get("id", "unknown"), completed_ids, stats)
        finally:
            for handle in outputs.values():  # Close output handles to flush JSONL content to disk.
                handle.close()
            operator_log.close()
            for operator in operators:  # Tear down operators in workflow order.
                operator.teardown()

        stats["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        stats["elapsed_seconds"] = round(time.time() - started, 3)
        stats["completed_count"] = len(completed_ids)
        stats["current_completed_count"] = len(completed_ids)
        stats["pending_count"] = max(0, stats["input_total_count"] - stats["current_completed_count"])
        stats["completed_ids"] = sorted(completed_ids)
        metrics_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
        report_path = run_output_paths["report"]
        write_report(report_path, stats)
        stats["report_path"] = str(report_path)
        return stats

    def _run_operator_on_items(
        self, operator: BaseOperator, items: list[dict[str, Any]], stats: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Run one operator over all samples, optionally with item-level concurrency.

        Business logic:
            1. Decide between serial and concurrent execution from workflow and step settings.
            2. Submit all current samples when concurrency is enabled and generate traces per item.
            3. Rebuild results in input order while preserving existing failure semantics.

        Args:
                operator (BaseOperator): Current workflow operator.
                items (list[dict[str, Any]]): Current sample list.
                stats (dict[str, Any]): Run statistics dictionary.

        Returns:
            list[dict[str, Any]]: Sample list after the current operator finishes.

        Examples:
            >>> isinstance([], list)
            True
        """
        concurrency = int(stats.get("concurrency", 1))
        if concurrency <= 1 or operator.config.get("concurrent", True) is False or len(items) <= 1:  # Fall back to serial mode when concurrency is disabled or the batch is too small.
            stats["serial_step_count"] += 1
            return [self._process_one_item(operator, item, stats) for item in items]

        stats["concurrency_enabled"] = True
        stats["parallelized_count"] += len(items)
        next_items = list(items)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self._process_one_item, operator, item, None): index for index, item in enumerate(items)}
            for future, index in futures.items():  # Write results back by original index to preserve output order.
                processed = future.result()
                if processed.get("operator_trace", [{}])[-1].get("status") == "failed":  # Aggregate failure counts on the main thread for concurrent execution.
                    stats["failed_count"] += 1
                next_items[index] = processed
        return next_items

    def _process_one_item(
        self, operator: BaseOperator, item: dict[str, Any], stats: dict[str, Any] | None
    ) -> dict[str, Any]:
        """Process one sample while preserving existing error semantics.

        Business logic:
            1. Call the current operator's `process` method.
            2. Append a success trace entry when processing succeeds.
            3. Mark the sample for review and record `operator_failed` when processing fails.

        Args:
                operator (BaseOperator): Current workflow operator.
                item (dict[str, Any]): Current sample dictionary.
                stats (dict[str, Any] | None): Run statistics dictionary updated directly in serial execution.

        Returns:
            dict[str, Any]: Processed sample dictionary.

        Examples:
            >>> isinstance({}, dict)
            True
        """
        before = time.time()
        try:
            processed = operator.process(item)
            trace = {
                "sample_id": processed.get("id"),
                "operator": operator.operator_name,
                "status": "success",
                "latency_ms": round((time.time() - before) * 1000, 3),
                "issues": list(processed.get("issues", [])),
                "action": processed.get("action", "pending"),
            }
            processed["operator_trace"].append(trace)
            return processed
        except Exception as exc:
            if stats is not None:  # Update run-level failure counts directly in serial execution.
                stats["failed_count"] += 1
            item.setdefault("issues", []).append("operator_failed")
            item["action"] = "review"
            item["error"] = str(exc)
            trace = {
                "sample_id": item.get("id"),
                "operator": operator.operator_name,
                "status": "failed",
                "latency_ms": round((time.time() - before) * 1000, 3),
                "issues": list(item.get("issues", [])),
                "action": item.get("action", "review"),
            }
            item["operator_trace"].append(trace)
            return item

    def _ordered_steps(self, steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Order workflow steps by DAG dependencies when needed.

        Business logic:
            1. Detect whether the workflow is running in DAG mode.
            2. Preserve the configured order for non-DAG mode.
            3. Topologically sort by `depends_on` and reject dependency cycles.

        Args:
                steps (list[dict[str, Any]]): Workflow step list.

        Returns:
            list[dict[str, Any]]: Ordered workflow steps.

        Examples:
            >>> _ordered_steps
            _ordered_steps
        """
        if self.config.get("workflow", {}).get("mode") != "dag":  # Preserve configured order outside DAG mode.
            return steps
        remaining = {step["id"]: step for step in steps}
        ordered: list[dict[str, Any]] = []
        done: set[str] = set()
        while remaining:
            ready = [
                step_id
                for step_id, step in remaining.items()
                if set(step.get("depends_on", [])) <= done
            ]
            if not ready:  # No ready node means a dependency cycle or unresolved dependency exists.
                cycle = ", ".join(sorted(remaining))
                raise ValueError(f"workflow dag has unresolved dependencies or a cycle: {cycle}")
            for step_id in ready:  # Move each ready step into the ordered list.
                ordered.append(remaining.pop(step_id))
                done.add(step_id)
        return ordered

    def _build_operators(self, steps: list[dict[str, Any]], run_dir: Path | None = None) -> list[BaseOperator]:
        """Create and initialize operator instances for workflow steps.

        Business logic:
            1. Iterate over the ordered step configuration.
            2. Create operator instances from the registry by operator name.
            3. Run setup on each operator and return the executable chain.

        Args:
                steps (list[dict[str, Any]]): Workflow step list.

        Returns:
            list[BaseOperator]: Initialized operator instances.

        Examples:
            >>> _build_operators
            _build_operators
        """
        operators: list[BaseOperator] = []
        for step in steps:  # Build operators one step at a time from workflow configuration.
            params = dict(step.get("params", {}))
            params["_runtime"] = {
                "base_dir": str(self.cwd.resolve(strict=False)),
                "run_dir": str((run_dir or self.cwd).resolve(strict=False)),
                "allowed_roots": [str(root) for root in self.allowed_roots] if self.allowed_roots is not None else None,
            }
            operator = self.registry.create(step["operator"], config=params)
            operator.setup()
            operators.append(operator)
        return operators

    def _read_jsonl(self, path: Path) -> Iterable[dict[str, Any]]:
        """Stream JSONL input line by line.

        Business logic:
            1. Read the JSONL file one line at a time.
            2. Skip blank lines directly.
            3. Build a review sample when JSON decoding fails.

        Args:
                path (Path): File path.

        Returns:
            Iterable[dict[str, Any]]: Parsed sample iterator.

        Examples:
            >>> _read_jsonl
            _read_jsonl
        """
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):  # Read line by line to support streaming JSONL processing.
                line = line.strip()
                if not line:  # Blank lines are ignored.
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
        """Fill default workflow fields on a sample.

        Business logic:
            1. Generate a unique identifier when the sample has no ID.
            2. Fill required workflow fields such as payload, meta, metrics, and issues.
            3. Set the initial action to `pending` for later quality-gate updates.

        Args:
                item (dict[str, Any]): Current sample dictionary.

        Returns:
            dict[str, Any]: Sample with default fields filled in.

        Examples:
            >>> _prepare_item
            _prepare_item
        """
        item.setdefault("id", f"sample_{time.time_ns()}")
        item.setdefault("modality", "unknown")
        item.setdefault("payload", {})
        item.setdefault("meta", {})
        item.setdefault("intermediate", {})
        item.setdefault("metrics", {})
        item.setdefault("issues", [])
        item.setdefault("operator_trace", [])
        item.setdefault("action", "pending")
        return item

    def _load_checkpoint(self, path: Path) -> set[str]:
        """Load resume checkpoint state from disk.

        Business logic:
            1. Return an empty set when the checkpoint file does not exist.
            2. Read JSON checkpoint content from disk.
            3. Convert `completed_ids` into a string set used to skip samples.

        Args:
                path (Path): File path.

        Returns:
            set[str]: Completed sample IDs loaded from the checkpoint.

        Examples:
            >>> _load_checkpoint
            _load_checkpoint
        """
        if not path.exists():  # Return an empty state when the checkpoint file is missing.
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        return {str(item) for item in data.get("completed_ids", [])}

    def _write_checkpoint(self, path: Path, workflow_id: str, completed_ids: set[str], stats: dict[str, Any] | None = None) -> None:
        """Write resume checkpoint state to disk.

        Business logic:
            1. Summarize the workflow ID and completed sample count.
            2. Write `completed_ids` in stable sorted order.
            3. Update the timestamp for resume auditing.

        Args:
                path (Path): Checkpoint file path.
                workflow_id (str): Workflow identifier.
                completed_ids (set[str]): Set of completed sample IDs.
                stats (dict[str, Any] | None): Current run statistics used for resume audit fields.

        Returns:
            None: The function writes the checkpoint file in place.

        Examples:
            >>> _write_checkpoint
            _write_checkpoint
        """
        payload = {
            "workflow_id": workflow_id,
            "status": "running",
            "resume_enabled": bool((stats or {}).get("resume_enabled", False)),
            "resume_count": int((stats or {}).get("resume_count", 0)),
            "input_total_count": int((stats or {}).get("input_total_count", 0)),
            "historical_completed_count": int((stats or {}).get("historical_completed_count", 0)),
            "newly_processed_count": int((stats or {}).get("newly_processed_count", 0)),
            "current_completed_count": len(completed_ids),
            "pending_count": int((stats or {}).get("pending_count", 0)),
            "completed_count": len(completed_ids),
            "completed_ids": sorted(completed_ids),
            "skipped_count": int((stats or {}).get("skipped_count", 0)),
            "processed_count": int((stats or {}).get("processed_count", 0)),
            "failed_count": int((stats or {}).get("failed_count", 0)),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
