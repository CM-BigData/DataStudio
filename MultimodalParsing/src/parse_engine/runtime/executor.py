from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from parse_engine.models import DataItem
from parse_engine.runtime.checkpoint import CheckpointStore
from parse_engine.runtime.config import WorkflowConfig
from parse_engine.runtime.input_adapter import InputAdapter
from parse_engine.runtime.metrics import collect_metrics
from parse_engine.runtime.registry import registry
from parse_engine.runtime.report import write_report


SUPPORTED_SUFFIXES = {  # Supported formats: file suffixes allowed for parsing.
    ".pdf",
    ".docx",
    ".xls",
    ".xlsx",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".wav",
    ".mp3",
    ".m4a",
    ".flac",
    ".aac",
}


class WorkflowExecutor:
    def __init__(self, config: WorkflowConfig, config_path: Path, resume: bool = False) -> None:
        """Initialize workflow executor runtime context.

        Business logic:
            1. Store the validated workflow configuration and configuration file path.
            2. Resolve the output directory from output configuration.
            3. Create a checkpoint store to record run progress.

        Args:
            config: Loaded workflow configuration object.
            config_path: Workflow configuration file path, used to resolve relative input and output paths.
            resume: Whether to read existing artifacts and skip completed samples.

        Returns:
            None: The constructor only builds executor state.

        Examples:
            >>> hasattr(WorkflowExecutor, "run")
        True"""
        self.config = config  # Workflow config: validated configuration used by the current executor.
        self.config_path = config_path  # Config path: path of the current workflow YAML file.
        self.run_dir = self._resolve_run_dir()  # Run directory: output directory where the current execution writes artifacts.
        self.resume = resume  # Resume mode: reuse existing output and skip successful samples when enabled.
        self.checkpoint = CheckpointStore(self.run_dir)  # Checkpoint store: records current run progress.

    def run(self) -> Path:
        """Execute the full content parsing workflow.

        Business logic:
            1. Create the run directory, copy the config file, and set the checkpoint to running.
            2. Load input samples and create, initialize, and execute all operators in order.
            3. Collect metrics, write output files, update the completed checkpoint state, and return the run directory.

        Args:
            None.

        Returns:
            Path: Run directory for this workflow execution.

        Examples:
            >>> hasattr(WorkflowExecutor, "_write_outputs")
            True"""
        self.run_dir.mkdir(parents=True, exist_ok=True)
        workflow_copy_path = self.run_dir / "workflow.yaml"
        if self.config_path.resolve() != workflow_copy_path.resolve():
            shutil.copyfile(self.config_path, workflow_copy_path)
        completed_ids = self._load_completed_ids() if self.resume else set()
        loaded_items = self._load_input_items()
        input_total_count = len(loaded_items)
        skipped_count = sum(1 for item in loaded_items if item.id in completed_ids)
        pending_items = [item for item in loaded_items if item.id not in completed_ids]
        self.checkpoint.update(
            status="running",
            workflow_id=self.config.workflow.id,
            resume_enabled=self.resume,
            resume_count=1 if self.resume else 0,
            input_total_count=input_total_count,
            historical_completed_count=skipped_count,
            newly_processed_count=0,
            current_completed_count=len(completed_ids),
            pending_count=len(pending_items),
            completed_count=len(completed_ids),
            completed_ids=sorted(completed_ids),
            skipped_count=skipped_count,
            processed_count=0,
            failed_count=0,
        )

        operators = [registry.create(step.operator, step.params) for step in self.config.steps]
        concurrency = max(1, int(self.config.workflow.concurrency))
        concurrency_stats = {
            "concurrency": concurrency,
            "concurrency_enabled": False,
            "parallelized_count": 0,
            "serial_step_count": 0,
        }

        for operator in operators:  # Preparation phase: initialize resources for each operator in workflow order.
            operator.setup()

        try:
            items = pending_items
            for operator in operators:  # Pipeline phase: output of the previous step becomes input to the next operator.
                items = self._run_operator_on_items(operator, items, concurrency, concurrency_stats)
                self.checkpoint.update(processed=len(items), processed_count=len(items), skipped_count=skipped_count)
        finally:
            for operator in operators:  # Cleanup phase: ensure that every created operator releases resources.
                operator.teardown()

        newly_success_count = sum(1 for item in items if item.action != "failed")
        current_completed_count = skipped_count + newly_success_count
        metrics = collect_metrics(items)
        metrics.update(
            {
                "input_total_count": input_total_count,
                "historical_completed_count": skipped_count,
                "newly_processed_count": len(items),
                "current_completed_count": current_completed_count,
                "pending_count": max(0, input_total_count - current_completed_count),
                "resume_enabled": self.resume,
                "resume_count": 1 if self.resume else 0,
                "skipped_count": skipped_count,
                "processed_count": len(items),
                "completed_count": current_completed_count,
                **concurrency_stats,
            }
        )
        self._write_outputs(items, metrics, append=self.resume)
        self.checkpoint.update(
            status="completed",
            processed=len(items),
            processed_count=len(items),
            success=newly_success_count,
            failed=sum(1 for item in items if item.action == "failed"),
            failed_count=sum(1 for item in items if item.action == "failed"),
            input_total_count=input_total_count,
            historical_completed_count=skipped_count,
            newly_processed_count=len(items),
            current_completed_count=current_completed_count,
            pending_count=max(0, input_total_count - current_completed_count),
            completed_count=current_completed_count,
            completed_ids=sorted({item.id for item in loaded_items if item.id in completed_ids} | {item.id for item in items if item.action != "failed"}),
            skipped_count=skipped_count,
            resume_enabled=self.resume,
        )
        return self.run_dir

    def _run_operator_on_items(
        self, operator: object, items: List[DataItem], concurrency: int, stats: dict
    ) -> List[DataItem]:
        """Run sample-level concurrent processing for a single operator.

        Business logic:
            1. Decide between serial and concurrent execution from workflow concurrency and step concurrent settings.
            2. In concurrent mode, submit only non-failed samples and pass failed samples through directly.
            3. Rebuild results in input order while preserving current exception semantics.

        Args:
            operator (object): Current workflow operator.
            items (List[DataItem]): Current list of samples to process.
            concurrency (int): Concurrency level for this run.
            stats (dict): Concurrency audit statistics dictionary.

        Returns:
            List[DataItem]: Sample list after processing by the current operator.

        Examples:
            >>> isinstance([], list)
            True"""
        active_indexes = [index for index, item in enumerate(items) if item.action != "failed"]
        if concurrency <= 1 or getattr(operator, "config", {}).get("concurrent", True) is False or len(active_indexes) <= 1:  # Serial conditions: global concurrency off, step-level concurrency disabled, or too few valid samples.
            stats["serial_step_count"] += 1
            return [self._process_one_item(operator, item) if item.action != "failed" else item for item in items]

        stats["concurrency_enabled"] = True
        stats["parallelized_count"] += len(active_indexes)
        next_items = list(items)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self._process_one_item, operator, items[index]): index for index in active_indexes}
            for future, index in futures.items():  # Future mapping: fill results back by original index to preserve output order.
                next_items[index] = future.result()
        return next_items

    def _process_one_item(self, operator: object, item: DataItem) -> DataItem:
        """Process a single parsing sample while preserving current exception semantics.

        Business logic:
            1. Call process on the current operator.
            2. Catch exceptions and mark the sample as failed.
            3. Write operator_error information for reporting and auditing.

        Args:
            operator (object): Current workflow operator.
            item (DataItem): Current sample.

        Returns:
            DataItem: Processed sample.

        Examples:
            >>> isinstance("operator_error", str)
            True"""
        try:
            return operator.process(item)
        except Exception as exc:
            item.action = "failed"
            item.issues.append(
                {
                    "type": "operator_error",
                    "operator": operator.operator_name,
                    "message": str(exc),
                }
            )
            return item

    def _load_input_items(self) -> List[DataItem]:
        """Load workflow input into a list of DataItem objects.

        Business logic:
            1. Resolve absolute input paths from configuration, including relative paths under the config file parent.
            2. For directory input, recursively filter non-hidden files with supported suffixes; for file input, use the single file directly.
            3. Create DataItem objects from sorted paths one by one to keep output order stable.

        Args:
            None.

        Returns:
            List[DataItem]: List of data items ready to enter the operator pipeline.

        Examples:
            >>> isinstance([], list)
            True"""
        adapter = InputAdapter(self.config.input.model_dump(exclude_none=True), base_dir=self.config_path.parent.parent)
        return list(adapter.read())

    def _resolve_run_dir(self) -> Path:
        """Compute the output directory for this workflow execution.

        Business logic:
            1. Read output.path and resolve relative paths from the configuration file location.
            2. Use the configured output directory directly so multiple tools can be chained.
            3. Return the directory used for fresh runs and resume.

        Args:
            None.

        Returns:
            Path: Output directory that this execution should write into.

        Examples:
            >>> isinstance(Path("."), Path)
            True"""
        if not self.config.output.path:  # Output config: output.path must be declared for the run directory.
            raise ValueError("output.path is required")
        output_path = Path(self.config.output.path)
        if not output_path.is_absolute():  # Relative output path: write under the project directory containing the config file.
            output_path = self.config_path.parent.parent / output_path
        return output_path

    def _write_outputs(self, items: List[DataItem], metrics: dict, append: bool = False) -> None:
        """Write workflow artifacts, failed samples, metrics, and the report.

        Business logic:
            1. Write all DataItem objects to artifacts.jsonl line by line.
            2. Write samples whose action is failed to failed.jsonl and also write metrics.json.
            3. Call the report module to generate report.md.

        Args:
            items: List of data items after workflow processing has finished.
            metrics: Summary metrics dictionary generated by collect_metrics.
            append: Whether to append to existing output files.

        Returns:
            None: Output files are written directly into the run directory.

        Examples:
            >>> isinstance({"total": 0}, dict)
            True"""
        artifacts_path = self.run_dir / "artifacts.jsonl"
        failed_path = self.run_dir / "failed.jsonl"
        metrics_path = self.run_dir / "metrics.json"

        mode = "a" if append else "w"
        with artifacts_path.open(mode, encoding="utf-8") as fh:
            for item in items:  # Full artifact output: each sample corresponds to one JSON line.
                fh.write(item.model_dump_json() + "\n")

        with failed_path.open(mode, encoding="utf-8") as fh:
            for item in items:  # Failed output write: filter samples that require investigation.
                if item.action == "failed":  # Failed sample: write separately to failed.jsonl for quick location.
                    fh.write(item.model_dump_json() + "\n")

        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(self.run_dir, metrics, items)

    def _load_completed_ids(self) -> set[str]:
        """Read sample ids that have already been written successfully.

        Business logic:
            1. Locate artifacts.jsonl in the current run directory.
            2. Parse sample results line by line and ignore empty lines.
            3. Treat samples whose action is not failed as completed.

        Args:
            None.

        Returns:
            set[str]: Set of completed sample ids.

        Examples:
            >>> isinstance(set(), set)
            True"""
        artifacts_path = self.run_dir / "artifacts.jsonl"
        if not artifacts_path.exists():  # First run: there are no recoverable artifacts yet.
            return set()
        completed: set[str] = set()
        with artifacts_path.open("r", encoding="utf-8") as handle:
            for line in handle:  # Recover line by line to avoid loading large JSONL artifacts all at once.
                if not line.strip():  # Empty lines are not valid samples.
                    continue
                row = json.loads(line)
                if row.get("id") and row.get("action") != "failed":  # Only non-failed samples can be skipped on resume.
                    completed.add(str(row["id"]))
        return completed
