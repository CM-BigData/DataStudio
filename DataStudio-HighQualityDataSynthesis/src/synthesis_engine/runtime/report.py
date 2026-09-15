from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable

from synthesis_engine.models import GenerationItem


def write_report(run_dir: Path, metrics: Dict[str, Any], items: Iterable[GenerationItem]) -> Path:
    """Write the workflow Markdown report

    Business logic:
        1. Collect metrics and filtered samples
        2. Build Markdown report lines
        3. Write the report into the run directory and return its path

    Args:
        run_dir (Path): Workflow run directory.
        metrics (Dict[str, Any]): Aggregated metrics dictionary.
        items (Iterable[GenerationItem]): Final sample collection.

    Returns:
        Path: Path to the generated report file.

    Examples:
        >>> callable(write_report)
        True
    """
    item_list = list(items)
    report_path = run_dir / "report.md"
    lines = [
        "# Data Synthesis Report",
        "",
        f"- Total samples: {metrics.get('input_total_count', metrics.get('total', 0))}",
        f"- Current run samples: {metrics.get('total', 0)}",
        f"- Task types: `{json.dumps(metrics.get('by_task_type', {}), ensure_ascii=False)}`",
        f"- Actions: `{json.dumps(metrics.get('by_action', {}), ensure_ascii=False)}`",
        f"- Issue types: `{json.dumps(metrics.get('issues', {}), ensure_ascii=False)}`",
        f"- Average quality score: {metrics.get('avg_quality_score', 0)}",
        f"- Average diversity score: {metrics.get('avg_diversity_score', 0)}",
        f"- Resume enabled: {metrics.get('resume_enabled', False)}",
        f"- Skipped count: {metrics.get('skipped_count', 0)}",
        f"- Processed count: {metrics.get('processed_count', metrics.get('total', 0))}",
        f"- Completed count: {metrics.get('completed_count', 0)}",
        f"- Historical completed count: {metrics.get('historical_completed_count', metrics.get('skipped_count', 0))}",
        f"- Newly processed count: {metrics.get('newly_processed_count', metrics.get('processed_count', metrics.get('total', 0)))}",
        f"- Current completed count: {metrics.get('current_completed_count', metrics.get('completed_count', 0))}",
        f"- Pending count: {metrics.get('pending_count', max(0, metrics.get('input_total_count', metrics.get('total', 0)) - metrics.get('completed_count', 0)))}",
        f"- Concurrency: {metrics.get('concurrency', 1)}",
        f"- Concurrency enabled: {metrics.get('concurrency_enabled', False)}",
        f"- Parallelized count: {metrics.get('parallelized_count', 0)}",
        "",
        "## Filtered Samples",
        "",
    ]
    filtered = [item for item in item_list if item.action == "filtered"]
    if not filtered:  # Write an explicit none marker when no samples were filtered.
        lines.append("None.")
    else:
        for item in filtered:  # List filtered samples one by one to make manual auditing easier.
            lines.append(f"- `{item.id}`: {item.issues}")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path
