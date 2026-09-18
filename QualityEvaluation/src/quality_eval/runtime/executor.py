from __future__ import annotations

import json
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

import quality_eval.operators  # noqa: F401

from .checkpoint import CheckpointManager
from .dag import DAGBuilder
from .error_queue import ErrorQueue
from .io import DataReader, DataWriter
from .metrics import MetricsCollector
from .path_security import safe_path, validate_task_id
from .registry import registry
from .registry import load_custom_operators
from .report import build_summary, write_markdown_report
from .scheduler import TaskScheduler
from .schema import SchemaValidator


class WorkflowExecutor:
    def __init__(
        self,
        config: dict[str, Any],
        config_path: Path,
        task_id: str | None = None,
        output_dir: Path | None = None,
        resume: bool = False,
        workers: int | None = None,
        allowed_roots: Sequence[Path] | None = None,
    ) -> None:
        """Initialize the workflow executor.

        Business logic:
            1. Store config, paths, and task ID.
            2. Derive the project directory and relative-path base from the workflow file location.
            3. Merge command-line arguments with runtime config to determine concurrency, batch size, and retry count.
            4. Resolve output, checkpoint, log, and error-queue paths.
            5. Initialize context, metrics collector, and error queue.

        Args:
            config (dict[str, Any]): Full workflow configuration.
            config_path (Path): Workflow configuration file path.
            task_id (str | None, optional): Task ID specified by the command-line.
            output_dir (Path | None, optional): Output directory overridden by the command-line.
            resume (bool, optional): Whether to resume from existing results.
            workers (int | None, optional): Concurrency overridden by the command-line.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> isinstance(WorkflowExecutor, type)
            True
        """
        self.config = config  # Full workflow config used for validation, operator construction, and summarization.
        self.config_path = config_path  # Workflow config path used to resolve relative input and output paths.
        self.base_dir = config_path.parent.resolve()  # Config directory used as the preferred relative-path base.
        self.project_dir = self.base_dir.parent if self.base_dir.name == "workflows" else self.base_dir  # Project directory used as a fallback when configs live under workflows/.
        self.allowed_roots = tuple(allowed_roots) if allowed_roots is not None else None
        self.workflow = config["workflow"]  # Workflow section storing execution mode, task type, and batch settings.
        generated_task_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.task_id = validate_task_id(task_id if task_id is not None else generated_task_id)  # Safe filename component used for outputs and checkpoints.
        self.resume = resume  # Resume switch that controls whether existing results are reused to skip processed samples.
        runtime = config.get("runtime", {})
        self.workers = workers or int(runtime.get("workers") or self.workflow.get("concurrency", 1) or 1)  # Worker count with command-line values taking precedence over config.
        self.batch_size = int(runtime.get("batch_size") or self.workflow.get("batch_size", 1) or 1)  # Batch size used to split pending samples.
        self.executor_type = runtime.get("executor", "thread")  # Executor type kept as a config field for future extension.
        self.retry_times = int(runtime.get("retry_times", 0) or 0)  # Operator retry count controlling extra attempts after failures.
        self.paths = self._resolve_output_paths(output_dir)  # Output-path collection covering results, summaries, reports, logs, and the error queue.
        self.context: dict[str, Any] = {"task_id": self.task_id}  # Shared cross-operator context storing task ID and duplicate-sample lists.
        self.operator_logs: list[dict[str, Any]] = []  # Operator audit log storing the execution result of each operator on each sample.
        self.metrics = MetricsCollector()  # Metrics collector summarizing sample counts, failures, latency, and issue distribution.
        self.error_queue = ErrorQueue(self.paths["error_path"])  # Error queue that records samples with operator exceptions.

    def run(self) -> dict[str, Any]:
        """Run the full quality-evaluation workflow.

        Business logic:
            1. Validate workflow config, operator registration, and input paths.
            2. Read samples and build the dependency-ordered operator list.
            3. Call operator setup hooks to prepare full-sample indexes or shared context.
            4. Skip existing results when resuming and process only pending samples.
            5. Write sample results, checkpoint data, metrics, summary, Markdown report, and audit logs.
            6. Call operator teardown hooks to finish cleanup.

        Args:
            None.

        Returns:
            dict[str, Any]: Dataset-level summary result.

        Examples:
            >>> callable(WorkflowExecutor.run)
            True
        """
        load_custom_operators(
            self.config.get("custom_operators"),
            base_dir=self.config_path.parent.resolve(),
            allowed_roots=self.allowed_roots,
        )
        SchemaValidator().validate_config(self.config, registry=registry)
        SchemaValidator().validate_paths(self.config, self._resolve_path)
        items = self._read_items()
        operators = self._build_operators()
        for operator in operators:  # Setup may need the full sample set before per-sample processing starts.
            operator.setup(items, self.context)

        checkpoint = CheckpointManager(
            self.paths["checkpoint_path"],
            self.task_id,
            self.workflow.get("id", "workflow"),
            resume_enabled=self.resume,
        )
        checkpoint.load()

        existing_results = self._load_existing_results() if self.resume else []
        if self.resume:  # Resume mode loads old trace logs first so the final rewrite does not lose historical traces.
            self.operator_logs = self._load_existing_logs()  # Old trace logs are reused in summaries and written back on resume.
        processed_ids = {item["sample_id"] for item in existing_results}
        pending_items = [item for item in items if item["id"] not in processed_ids]
        checkpoint.start(len(items), skipped_count=len(processed_ids), pending_count=len(pending_items))

        self.paths["result_path"].parent.mkdir(parents=True, exist_ok=True)
        mode = "a" if self.resume and self.paths["result_path"].exists() else "w"
        started = time.perf_counter()
        results = list(existing_results)
        with self.paths["result_path"].open(mode, encoding="utf-8") as result_handle:
            if self.workers > 1 and len(pending_items) > 1:  # Multithreading is enabled only when both worker count and pending-item count are sufficient.
                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    futures = [
                        pool.submit(self._process_batch, batch, operators)
                        for batch in self._batches(pending_items)
                    ]
                    for future in as_completed(futures):  # Collect finished batches in completion order to improve throughput.
                        for result in future.result():  # Preserve sample order inside each batch.
                            self._write_result(result_handle, result)
                            self.metrics.record_sample(result)
                            results.append(result)
                            checkpoint.mark_sample(
                                result["sample_id"],
                                result.get("status", "success"),
                                "done",
                                result["action"],
                                result["score"],
                                trace_info=result.get("trace_summary"),
                            )
            else:
                for batch in self._batches(pending_items):  # Single-thread mode still moves in batches to stay consistent with the concurrent path.
                    for item in batch:  # Sequential execution is easier to debug and reproduce.
                        result = self._process_item(item, operators)
                        self._write_result(result_handle, result)
                        self.metrics.record_sample(result)
                        results.append(result)
                        checkpoint.mark_sample(
                            result["sample_id"],
                            result.get("status", "success"),
                            "done",
                            result["action"],
                            result["score"],
                            trace_info=result.get("trace_summary"),
                        )

        for result in existing_results:  # Existing results must also contribute to the final metrics snapshot during resume.
            self.metrics.record_sample(result)

        elapsed_ms = (time.perf_counter() - started) * 1000
        metrics_snapshot = self.metrics.snapshot()
        paths_for_summary = {key: str(value) for key, value in self.paths.items()}
        duplicate_ids = self.context.get("text_duplicate_ids") or self.context.get("image_duplicate_ids") or []
        summary = build_summary(
            task_id=self.task_id,
            workflow_id=self.workflow.get("id", "workflow"),
            modality=self.workflow.get("task_type", "unknown"),
            results=results,
            elapsed_ms=elapsed_ms,
            paths=paths_for_summary,
            operator_logs=self.operator_logs,
            duplicate_ids=duplicate_ids,
            metrics_snapshot=metrics_snapshot,
            score_weights=self.config.get("score_weights") or self.config.get("rules", {}).get("score_weights"),
        )
        summary["resume_enabled"] = self.resume
        summary["resume_count"] = 1 if self.resume else 0
        summary["input_total_count"] = len(items)
        summary["historical_completed_count"] = len(processed_ids)
        summary["newly_processed_count"] = len(pending_items)
        summary["current_completed_count"] = len(results)
        summary["pending_count"] = max(0, len(items) - len(results))
        summary["skipped_count"] = len(processed_ids)
        summary["processed_count"] = len(pending_items)
        summary["completed_count"] = len(results)
        summary["completed_ids"] = sorted(str(result["sample_id"]) for result in results)
        DataWriter.write_json(self.paths["summary_path"], summary)
        write_markdown_report(summary, self.paths["report_path"])
        self._write_logs()
        checkpoint.finish()
        for operator in operators:  # Release any resources operators may still hold after workflow completion.
            operator.teardown()
        return summary

    def _process_batch(self, items: list[dict[str, Any]], operators: list[Any]) -> list[dict[str, Any]]:
        """Process one sample batch.

        Business logic:
            1. Receive one batch split by the executor.
            2. Call the per-sample processing logic for each sample.
            3. Keep result order aligned with input order inside the batch.

        Args:
            items (list[dict[str, Any]]): Batch of samples to process.
            operators (list[Any]): Instantiated and ordered operator list.

        Returns:
            list[dict[str, Any]]: Batch processing result list.

        Examples:
            >>> callable(WorkflowExecutor._process_batch)
            True
        """
        return [self._process_item(item, operators) for item in items]

    def _batches(self, items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
        """Split the sample list by batch size.

        Business logic:
            1. Slice from index 0 using `batch_size` as the step size.
            2. Preserve original sample order.
            3. Return the batch list for single-threaded or thread-pool processing.

        Args:
            items (list[dict[str, Any]]): Sample list to split.

        Returns:
            list[list[dict[str, Any]]]: Sample batch list.

        Examples:
            >>> executor = object.__new__(WorkflowExecutor)
            >>> executor.batch_size = 2
            >>> executor._batches([1, 2, 3])
            [[1, 2], [3]]
        """
        return [items[index : index + self.batch_size] for index in range(0, len(items), self.batch_size)]

    def _process_item(self, item: dict[str, Any], operators: list[Any]) -> dict[str, Any]:
        """Execute the full operator chain for one sample.

        Business logic:
            1. Deep-copy the sample to avoid mutating the original read result.
            2. Execute ordered operators one by one.
            3. Retry a failing operator according to `retry_times` and record retry attempts.
            4. Write final failures into issues, metrics, and the error queue.
            5. Record an audit log for each operator and return the standardized result.

        Args:
            item (dict[str, Any]): Sample to process.
            operators (list[Any]): Instantiated and ordered operator list.

        Returns:
            dict[str, Any]: Standardized sample result.

        Examples:
            >>> callable(WorkflowExecutor._process_item)
            True
        """
        current = json.loads(json.dumps(item, ensure_ascii=False))
        item_status = "success"
        trace_id = self._trace_id(current["id"])
        sample_trace: list[dict[str, Any]] = []
        for index, operator in enumerate(operators, start=1):  # Every sample must pass through all operators in DAG order.
            started = time.perf_counter()
            before_payload = self._stable_json(current)
            before_size = len(before_payload)
            input_hash = self._hash_payload(current)
            config_hash = self._hash_payload(getattr(operator, "config", {}))
            status = "success"
            last_error: Exception | None = None
            retry_attempt = 1
            for attempt in range(self.retry_times + 1):  # `retry_times` counts extra attempts after the first failure.
                retry_attempt = attempt + 1
                try:
                    current = operator.process(current)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    current.setdefault("metrics", {})[f"{operator.operator_name}_retry_attempt"] = attempt + 1
            if last_error is not None:  # Mark the sample as an operator failure when all retries still fail.
                status = "failed"
                item_status = "failed"
                current.setdefault("issues", []).append("operator_error")
                current.setdefault("metrics", {})[f"{operator.operator_name}_error"] = str(last_error)
                self.error_queue.push(current, str(last_error), operator.operator_name)
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            self.metrics.record_operator_latency(latency_ms)
            output_payload = self._stable_json(current)
            event = {
                "task_id": self.task_id,
                "run_id": self.task_id,
                "workflow_id": self.workflow.get("id", "workflow"),
                "trace_id": trace_id,
                "sample_id": current["id"],
                "step_id": f"{index}:{operator.operator_name}",
                "operator": operator.operator_name,
                "operator_version": operator.operator_version,
                "version": operator.operator_version,
                "status": status,
                "retry_attempt": retry_attempt,
                "latency_ms": latency_ms,
                "input_hash": input_hash,
                "output_hash": self._hash_text(output_payload),
                "input_size": before_size,
                "output_size": len(output_payload),
                "config_hash": config_hash,
                "issues": list(current.get("issues", [])),
                "score": current.get("score"),
                "action": current.get("action"),
                "error": str(last_error) if last_error is not None else None,
                "source": item.get("source", {}),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            sample_trace.append(event)
            self.operator_logs.append(event)
        return self._format_result(current, item_status, sample_trace)

    def _format_result(self, item: dict[str, Any], status: str = "success", trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Convert an internal sample into the output result structure.

        Business logic:
            1. Preserve task ID, sample ID, modality, and status.
            2. Read score, level, metrics, issues, action, and suggestions.
            3. Add sample-level `trace_id`, `trace_summary`, and trace steps.
            4. Provide defaults for missing fields so the result JSONL structure stays stable.

        Args:
            item (dict[str, Any]): Internal sample after operator processing.
            status (str, optional): Sample processing status.
            trace (list[dict[str, Any]] | None, optional): Operator trace list traversed by the sample.

        Returns:
            dict[str, Any]: Sample result ready to be written into result JSONL.

        Examples:
            >>> executor = object.__new__(WorkflowExecutor)
            >>> executor.task_id = "task"
            >>> executor._format_result({"id": "s1", "modality": "text"})["sample_id"]
            's1'
        """
        trace = trace or []
        failed_steps = [step["step_id"] for step in trace if step.get("status") == "failed"]
        trace_id = trace[0]["trace_id"] if trace else self._trace_id(item["id"])
        trace_log_path = str(getattr(self, "paths", {}).get("log_path", ""))
        return {
            "task_id": self.task_id,
            "sample_id": item["id"],
            "modality": item["modality"],
            "status": status,
            "trace_id": trace_id,
            "trace_summary": {
                "trace_id": trace_id,
                "step_count": len(trace),
                "failed_step": failed_steps[0] if failed_steps else None,
                "status": status,
                "trace_event_count": len(trace),
                "trace_log_path": trace_log_path,
            },
            "trace": trace,
            "score": item.get("score", 0),
            "level": item.get("level", "poor"),
            "metrics": item.get("metrics", {}),
            "issues": item.get("issues", []),
            "action": item.get("action", "review"),
            "suggestions": item.get("suggestions", []),
        }

    def _build_operators(self) -> list[Any]:
        """Build the operator instance list from the workflow.

        Business logic:
            1. Build the workflow DAG with `DAGBuilder`.
            2. Generate execution order with `TaskScheduler`.
            3. Fetch operator classes from the registry by node operator name.
            4. Merge workflow config, step config, and rules before instantiating operators.

        Args:
            None.

        Returns:
            list[Any]: Instantiated and ordered operator list.

        Examples:
            >>> callable(WorkflowExecutor._build_operators)
            True
        """
        dag = DAGBuilder().build(self.config)
        ordered_nodes = TaskScheduler().order(dag)
        operators = []
        for node in ordered_nodes:  # Instantiate in scheduled order so execution-chain dependencies stay correct.
            operator_cls = registry.get(node.operator)
            operator_config = {
                **self.config,
                "step": node.config,
                "rules": self.config.get("rules", {}),
            }
            operators.append(operator_cls(operator_config))
        return operators

    def _read_items(self) -> list[dict[str, Any]]:
        """Read workflow input samples.

        Business logic:
            1. Create `DataReader` with the executor path resolver.
            2. Read workflow and input config.
            3. Return the normalized sample list.

        Args:
            None.

        Returns:
            list[dict[str, Any]]: Normalized sample list.

        Examples:
            >>> callable(WorkflowExecutor._read_items)
            True
        """
        return DataReader(self._resolve_path).read(self.workflow, self.config["input"])

    def _resolve_output_paths(self, output_dir: Path | None) -> dict[str, Path]:
        """Resolve all output-related paths.

        Business logic:
            1. Resolve result, summary, and report paths from config.
            2. Replace only the directory while preserving filenames when `output_dir` is provided by the command-line.
            3. Derive checkpoint, log, and error-queue directories from the summary-file directory.
            4. Return a unified path dictionary used by the whole executor flow.

        Args:
            output_dir (Path | None): command-line-overridden output directory.

        Returns:
            dict[str, Path]: Output-path dictionary.

        Examples:
            >>> callable(WorkflowExecutor._resolve_output_paths)
            True
        """
        output = self.config["output"]
        paths = {
            "result_path": self._resolve_path(output["result_path"]),
            "summary_path": self._resolve_path(output["summary_path"]),
            "report_path": self._resolve_path(output["report_path"]),
        }
        if output_dir:  # Keep configured filenames when the command-line overrides only the output directory.
            output_dir = safe_path(
                output_dir,
                name="output directory",
                allowed_roots=self.allowed_roots,
            )
            if output_dir.exists() and not output_dir.is_dir():
                raise ValueError("output directory must be a directory")
            paths = {
                key: safe_path(
                    value.name,
                    name=key.replace("_", " "),
                    base_dir=output_dir,
                    allowed_roots=(output_dir,),
                )
                for key, value in paths.items()
            }
        summary_root = paths["summary_path"].parent.resolve(strict=False)
        checkpoint_root = safe_path(
            "checkpoints",
            name="checkpoint directory",
            base_dir=summary_root,
            allowed_roots=(summary_root,),
        )
        log_root = safe_path(
            "logs",
            name="operator log directory",
            base_dir=summary_root,
            allowed_roots=(summary_root,),
        )
        error_root = safe_path(
            "errors",
            name="error queue directory",
            base_dir=summary_root,
            allowed_roots=(summary_root,),
        )
        paths["checkpoint_path"] = safe_path(
            f"{self.task_id}.json",
            name="checkpoint path",
            base_dir=checkpoint_root,
            allowed_roots=(checkpoint_root,),
        )
        paths["log_path"] = safe_path(
            f"{self.task_id}_operators.jsonl",
            name="operator log path",
            base_dir=log_root,
            allowed_roots=(log_root,),
        )
        paths["error_path"] = safe_path(
            f"{self.task_id}_errors.jsonl",
            name="error queue path",
            base_dir=error_root,
            allowed_roots=(error_root,),
        )
        return paths

    def _resolve_path(self, value: str | Path) -> Path:
        """Resolve a path declared in workflow configuration.

        Business logic:
            1. Return absolute paths directly.
            2. Resolve relative paths against the config-file directory first.
            3. Use the candidate path when it exists.
            4. Fall back to the project directory when it does not.

        Args:
            value (str | Path): Path value declared in config.

        Returns:
            Path: Resolved path.

        Examples:
            >>> executor = object.__new__(WorkflowExecutor)
            >>> executor.base_dir = Path(".").resolve()
            >>> executor.project_dir = Path(".").resolve()
            >>> isinstance(executor._resolve_path("pyproject.toml"), Path)
            True
        """
        candidate = safe_path(
            value,
            name="workflow path",
            base_dir=self.base_dir,
            allowed_roots=self.allowed_roots,
        )
        if candidate.exists():  # Prefer local references when a path exists next to the config file.
            return candidate
        fallback = safe_path(
            value,
            name="workflow path",
            base_dir=self.project_dir,
            allowed_roots=self.allowed_roots,
        )
        return candidate if fallback == candidate else fallback

    def _write_result(self, handle: Any, result: dict[str, Any]) -> None:
        """Write one sample result.

        Business logic:
            1. Receive the already opened result-file handle.
            2. Delegate JSONL appending to `DataWriter`.
            3. Keep the executor free from direct JSON serialization details.

        Args:
            handle (Any): Open result-file handle.
            result (dict[str, Any]): Sample result.

        Returns:
            None: Writes directly to the result file.

        Examples:
            >>> callable(WorkflowExecutor._write_result)
            True
        """
        DataWriter.append_jsonl(handle, result)

    def _load_existing_results(self) -> list[dict[str, Any]]:
        """Read existing results in resume mode.

        Business logic:
            1. Return an empty list when the result file does not exist.
            2. Read existing JSONL results line by line.
            3. Skip blank lines and parse JSON records.
            4. Return existing results so processed samples can be skipped and included in summaries.

        Args:
            None.

        Returns:
            list[dict[str, Any]]: Existing sample result list.

        Examples:
            >>> callable(WorkflowExecutor._load_existing_results)
            True
        """
        if not self.paths["result_path"].exists():  # No recoverable results exist on first run or when the output file is missing.
            return []
        results = []
        with self.paths["result_path"].open("r", encoding="utf-8") as handle:
            for line in handle:  # Parse JSONL results line by line so completed samples can be skipped efficiently.
                if line.strip():  # Blank lines are not valid result records.
                    results.append(json.loads(line))
        return results

    def _load_existing_logs(self) -> list[dict[str, Any]]:
        """Read existing trace/operator logs in resume mode.

        Business logic:
            1. Check whether the log file exists.
            2. Parse existing JSONL trace events line by line.
            3. Return old logs so they can be reused by this summary and final log rewrite.

        Args:
            None.

        Returns:
            list[dict[str, Any]]: Existing trace/operator log list.

        Examples:
            >>> callable(WorkflowExecutor._load_existing_logs)
            True
        """
        if not self.paths["log_path"].exists():  # No old trace can be restored on first run or when the log file is missing.
            return []
        logs = []
        with self.paths["log_path"].open("r", encoding="utf-8") as handle:
            for line in handle:  # Restore JSONL logs line by line to avoid loading very large log files at once.
                if line.strip():  # Skip blank lines because they are not valid JSONL records.
                    logs.append(json.loads(line))
        return logs

    def _write_logs(self) -> None:
        """Write operator audit logs.

        Business logic:
            1. Ensure the log directory exists.
            2. Open the operator log JSONL file in write mode.
            3. Write each in-memory operator log as one JSON line.

        Args:
            None.

        Returns:
            None: Writes directly to the log file.

        Examples:
            >>> callable(WorkflowExecutor._write_logs)
            True
        """
        self.paths["log_path"].parent.mkdir(parents=True, exist_ok=True)
        with self.paths["log_path"].open("w", encoding="utf-8") as handle:
            for log in self.operator_logs:  # Each record is an audit event for one sample passing through one operator.
                handle.write(json.dumps(log, ensure_ascii=False) + "\n")

    def _trace_id(self, sample_id: str) -> str:
        """Generate a sample-level trace ID.

        Business logic:
            1. Receive the sample ID.
            2. Combine `task_id` and `sample_id` into a stable trace identifier.
            3. Return a readable and reversible trace ID.

        Args:
            sample_id (str): Sample ID.

        Returns:
            str: Sample-level trace ID.

        Examples:
            >>> executor = object.__new__(WorkflowExecutor)
            >>> executor.task_id = "task"
            >>> executor._trace_id("s1")
            'task:s1'
        """
        return f"{self.task_id}:{sample_id}"

    def _hash_payload(self, payload: Any) -> str:
        """Compute a stable hash for a JSON-serializable object.

        Business logic:
            1. Serialize the object to JSON with sorted keys.
            2. Generate a content fingerprint with sha256.
            3. Return the hexadecimal digest for trace auditing.

        Args:
            payload (Any): Data to hash.

        Returns:
            str: sha256 hexadecimal digest.

        Examples:
            >>> WorkflowExecutor._hash_payload(object.__new__(WorkflowExecutor), {"a": 1})[:8]
            'f9d86028'
        """
        return self._hash_text(self._stable_json(payload))

    def _hash_text(self, text: str) -> str:
        """Compute the sha256 hash of text.

        Business logic:
            1. Encode the text as UTF-8.
            2. Compute the digest with sha256.
            3. Return the hexadecimal hash string.

        Args:
            text (str): Text to hash.

        Returns:
            str: sha256 hexadecimal digest.

        Examples:
            >>> WorkflowExecutor._hash_text(object.__new__(WorkflowExecutor), "x")[:8]
            '2d711642'
        """
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _stable_json(self, payload: Any) -> str:
        """Convert an object into stable JSON text.

        Business logic:
            1. Serialize JSON with sorted keys.
            2. Preserve non-ASCII content.
            3. Use `default=str` for objects such as `Path`.

        Args:
            payload (Any): Object to serialize.

        Returns:
            str: Stable JSON text.

        Examples:
            >>> WorkflowExecutor._stable_json(object.__new__(WorkflowExecutor), {"b": 2, "a": 1})
            '{"a": 1, "b": 2}'
        """
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
