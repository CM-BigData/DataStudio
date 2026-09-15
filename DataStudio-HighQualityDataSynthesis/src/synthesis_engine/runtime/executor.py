from __future__ import annotations

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.runtime.checkpoint import CheckpointStore
from synthesis_engine.runtime.config import WorkflowConfig
from synthesis_engine.runtime.input_adapter import InputAdapter
from synthesis_engine.runtime.metrics import collect_metrics
from synthesis_engine.runtime.registry import registry
from synthesis_engine.runtime.report import write_report


class WorkflowExecutor:
    def __init__(self, config: WorkflowConfig, config_path: Path, resume: bool = False) -> None:
        """Initialize the workflow executor

        Business logic:
            1. Store the config and config file path
            2. Resolve the output directory for this execution
            3. Create the checkpoint store

        Args:
            config (WorkflowConfig): Workflow configuration.
            config_path (Path): Configuration file path.
            resume (bool): Whether to read existing outputs and skip accepted samples.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> callable(WorkflowExecutor.__init__)
            True
        """
        self.config = config  # Normalized workflow configuration used by this executor.
        self.config_path = config_path  # Config file path used to resolve relative input and output paths.
        self.run_dir = self._resolve_run_dir()  # Output directory for the current workflow run.
        self.resume = resume  # Resume mode reuses existing outputs and skips accepted samples.
        self.checkpoint = CheckpointStore(self.run_dir)  # Checkpoint store that records run state.

    def run(self) -> Path:
        """Execute the full workflow

        Business logic:
            1. Prepare the run directory, copy config, and write a running checkpoint
            2. Load seed samples and execute all operators plus retry logic
            3. Write outputs, metrics, reports, and the completed checkpoint

        Args:
            None.

        Returns:
            Path: Run directory for this execution.

        Examples:
            >>> callable(WorkflowExecutor.run)
            True
        """
        self.run_dir.mkdir(parents=True, exist_ok=True)
        workflow_copy_path = self.run_dir / "workflow.yaml"
        if self.config_path.resolve() != workflow_copy_path.resolve():
            shutil.copyfile(self.config_path, workflow_copy_path)
        completed_ids = self._load_completed_ids() if self.resume else set()
        items = self._load_seed_items()
        input_total_count = len(items)
        skipped_count = sum(1 for item in items if item.id in completed_ids)
        pending_items = [item for item in items if item.id not in completed_ids]
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

        for operator in operators:  # Run setup on every operator first so resources are ready for processing.
            operator.setup()

        try:
            retry_limit = max(0, int(self.config.workflow.retry_limit))
            for attempt in range(retry_limit + 1):  # Include the initial execution plus configured retries.
                for item in pending_items:  # Record the current attempt in lineage for quality-gate decisions.
                    item.lineage["retry_attempt"] = attempt
                pending_items = self._run_once(pending_items, operators, concurrency, concurrency_stats)
                retry_items = [item for item in pending_items if item.action == "needs_retry"]
                if not retry_items or attempt >= retry_limit:  # Stop when no retry is needed or the limit has been reached.
                    break
                for item in retry_items:  # Clear per-attempt outputs before retry while preserving retry history.
                    item.action = "pending"
                    item.generated = {}
                    item.metrics = {}
                    item.issues = []
                    item.lineage.setdefault("retry_history", []).append({"attempt": attempt, "reason": "quality_gate"})
        finally:
            for operator in operators:  # Always attempt to release operator resources even when execution fails.
                operator.teardown()

        for item in pending_items:  # Convert remaining retry-required samples into filtered after retries are exhausted.
            if item.action == "needs_retry":  # Final outputs should not keep the intermediate needs_retry state.
                item.action = "filtered"
                item.issues.append({"type": "retry_limit_reached", "message": "quality gate requested retry"})

        newly_accepted_count = sum(1 for item in pending_items if item.action == "accepted")
        current_completed_count = skipped_count + newly_accepted_count
        metrics = collect_metrics(pending_items)
        metrics.update(
            {
                "input_total_count": input_total_count,
                "historical_completed_count": skipped_count,
                "newly_processed_count": len(pending_items),
                "current_completed_count": current_completed_count,
                "pending_count": max(0, input_total_count - current_completed_count),
                "resume_enabled": self.resume,
                "resume_count": 1 if self.resume else 0,
                "skipped_count": skipped_count,
                "processed_count": len(pending_items),
                "completed_count": current_completed_count,
                **concurrency_stats,
            }
        )
        self._write_outputs(pending_items, metrics)
        self.checkpoint.update(
            status="completed",
            processed=len(pending_items),
            processed_count=len(pending_items),
            accepted=newly_accepted_count,
            filtered=sum(1 for item in pending_items if item.action == "filtered"),
            failed=sum(1 for item in pending_items if item.action == "failed"),
            failed_count=sum(1 for item in pending_items if item.action == "failed"),
            input_total_count=input_total_count,
            historical_completed_count=skipped_count,
            newly_processed_count=len(pending_items),
            current_completed_count=current_completed_count,
            pending_count=max(0, input_total_count - current_completed_count),
            completed_count=current_completed_count,
            completed_ids=sorted({item.id for item in items if item.id in completed_ids} | {item.id for item in pending_items if item.action == "accepted"}),
            skipped_count=skipped_count,
            resume_enabled=self.resume,
        )
        return self.run_dir

    def _run_once(
        self, items: List[GenerationItem], operators: list[BaseOperator], concurrency: int, stats: dict
    ) -> List[GenerationItem]:
        """Execute one pass of the operator pipeline

        Business logic:
            1. Traverse operators in configured order
            2. Skip samples whose actions are already terminal
            3. Capture operator exceptions and mark samples as failed

        Args:
            items (List[GenerationItem]): Current list of samples to process.
            operators (list[BaseOperator]): Instantiated operator list.
            concurrency (int): Concurrency level for this run.
            stats (dict): Concurrency audit statistics dictionary.

        Returns:
            List[GenerationItem]: Samples after this pass.

        Examples:
            >>> callable(WorkflowExecutor._run_once)
            True
        """
        for operator in operators:  # Advance sample state through the pipeline in operator order.
            items = self._run_operator_on_items(operator, items, concurrency, stats)
            self.checkpoint.update(processed=len(items))
        return items

    def _run_operator_on_items(
        self, operator: BaseOperator, items: List[GenerationItem], concurrency: int, stats: dict
    ) -> List[GenerationItem]:
        """Run sample-level concurrent processing for one operator

        Business logic:
            1. Choose serial or concurrent mode from workflow concurrency and step concurrent settings
            2. Submit only non-terminal samples in concurrent mode and pass terminal samples through
            3. Rebuild results in input order while preserving current exception semantics

        Args:
            operator (BaseOperator): Current workflow operator.
            items (List[GenerationItem]): Current sample list.
            concurrency (int): Concurrency level for this run.
            stats (dict): Concurrency audit statistics dictionary.

        Returns:
            List[GenerationItem]: Samples after processing by the current operator.

        Examples:
            >>> isinstance([], list)
            True
        """
        active_indexes = [index for index, item in enumerate(items) if item.action not in {"failed", "filtered", "accepted"}]
        if concurrency <= 1 or operator.config.get("concurrent", True) is False or len(active_indexes) <= 1:  # Fall back to serial mode when global concurrency is off, the step disables it, or too few active samples remain.
            stats["serial_step_count"] += 1
            return [self._process_one_item(operator, item) if index in active_indexes else item for index, item in enumerate(items)]

        stats["concurrency_enabled"] = True
        stats["parallelized_count"] += len(active_indexes)
        next_items = list(items)
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            futures = {pool.submit(self._process_one_item, operator, items[index]): index for index in active_indexes}
            for future, index in futures.items():  # Fill results back by original index to preserve output order.
                next_items[index] = future.result()
        return next_items

    def _process_one_item(self, operator: BaseOperator, item: GenerationItem) -> GenerationItem:
        """Process one synthesis sample while preserving current exception semantics

        Business logic:
            1. Call the current operator's process method
            2. Catch exceptions and mark the sample as failed
            3. Write operator_error for reporting and auditing

        Args:
            operator (BaseOperator): Current workflow operator.
            item (GenerationItem): Current sample.

        Returns:
            GenerationItem: Processed sample.

        Examples:
            >>> isinstance("operator_error", str)
            True
        """
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

    def _load_seed_items(self) -> List[GenerationItem]:
        """Load input seed samples

        Business logic:
            1. Resolve the input path from config
            2. Read the YAML items list
            3. Convert each record into a GenerationItem

        Args:
            None.

        Returns:
            List[GenerationItem]: Normalized seed sample list.

        Examples:
            >>> callable(WorkflowExecutor._load_seed_items)
            True
        """
        return list(InputAdapter(self.config.input.__dict__, self.config_path.parent.parent).read())

    def _resolve_run_dir(self) -> Path:
        """Resolve the output directory for the current run

        Business logic:
            1. Read the output path from config
            2. Resolve relative paths from the project root containing the config file
            3. Use the configured output directory directly for serial tool chaining

        Args:
            None.

        Returns:
            Path: Run directory for the current execution.

        Examples:
            >>> callable(WorkflowExecutor._resolve_run_dir)
            True
        """
        output_path = Path(self.config.output.path)
        if not output_path.is_absolute():  # Resolve relative output paths from the project root containing the config file.
            output_path = self.config_path.parent.parent / output_path
        return output_path

    def _write_outputs(self, items: List[GenerationItem], metrics: dict) -> None:
        """Write workflow output files

        Business logic:
            1. Write accepted samples to generated.jsonl
            2. Write filtered and failed samples to filtered.jsonl
            3. Write metrics JSON and generate the Markdown report

        Args:
            items (List[GenerationItem]): Final sample list.
            metrics (dict): Aggregated metrics dictionary.

        Returns:
            None: Writes output files into the run directory.

        Examples:
            >>> callable(WorkflowExecutor._write_outputs)
            True
        """
        generated_path = self.run_dir / "generated.jsonl"
        filtered_path = self.run_dir / "filtered.jsonl"
        metrics_path = self.run_dir / "metrics.json"

        mode = "a" if self.resume else "w"
        with generated_path.open(mode, encoding="utf-8") as fh:
            for item in items:  # Write only quality-gate accepted samples to generated output.
                if item.action == "accepted":  # accepted is the only deliverable sample action.
                    fh.write(item.to_json() + "\n")

        with filtered_path.open(mode, encoding="utf-8") as fh:
            for item in items:  # Keep filtered and failed samples in audit output.
                if item.action in {"filtered", "failed"}:  # Both non-deliverable actions share filtered.jsonl.
                    fh.write(item.to_json() + "\n")

        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(self.run_dir, metrics, items)

    def _load_completed_ids(self) -> set[str]:
        """Read IDs of accepted samples already written to disk

        Business logic:
            1. Locate generated.jsonl under the current run directory
            2. Parse generated samples line by line
            3. Treat samples whose action is accepted as completed

        Args:
            None.

        Returns:
            set[str]: Set of completed sample IDs.

        Examples:
            >>> isinstance(set(), set)
            True
        """
        generated_path = self.run_dir / "generated.jsonl"
        if not generated_path.exists():  # The first run has no persisted accepted samples to resume from.
            return set()
        completed: set[str] = set()
        with generated_path.open("r", encoding="utf-8") as handle:
            for line in handle:  # Recover line by line to avoid loading large JSONL artifacts at once.
                if not line.strip():  # Empty lines are not valid samples.
                    continue
                row = json.loads(line)
                if row.get("id") and row.get("action") == "accepted":  # Only accepted samples can be skipped on resume.
                    completed.add(str(row["id"]))
        return completed
