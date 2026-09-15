from __future__ import annotations

from pathlib import Path
from typing import Any


def write_report(path: Path, stats: dict[str, Any]) -> None:
    """Generate a Markdown workflow execution report.

    Business logic:
        1. Read workflow statistics collected during execution.
        2. Build issue distribution and summary rate sections.
        3. Write the final Markdown report to disk.

    Args:
            path (Path): Output file path.
            stats (dict[str, Any]): Workflow statistics dictionary.

    Returns:
        None: The function writes the report file in place.

    Examples:
        >>> callable(write_report)
        True
    """
    issues = stats.get("issue_distribution", {})
    issue_lines = "\n".join(
        f"| {issue} | {count} |" for issue, count in sorted(issues.items(), key=lambda pair: (-pair[1], pair[0]))
    )
    if not issue_lines:  # Write a placeholder row when no issues were recorded.
        issue_lines = "| none | 0 |"

    total = max(int(stats.get("total_count", 0)), 1)
    keep_rate = stats.get("keep_count", 0) / total
    drop_rate = stats.get("drop_count", 0) / total
    review_rate = stats.get("review_count", 0) / total

    content = f"""# Denoising Report

## Run Overview

| Metric | Value |
| --- | ---: |
| workflow_id | {stats.get("workflow_id")} |
| total_count | {stats.get("input_total_count", stats.get("total_count", 0))} |
| current_run_count | {stats.get("current_run_count", stats.get("processed_count", stats.get("total_count", 0)))} |
| keep_count | {stats.get("keep_count", 0)} |
| drop_count | {stats.get("drop_count", 0)} |
| review_count | {stats.get("review_count", 0)} |
| failed_count | {stats.get("failed_count", 0)} |
| resume_enabled | {stats.get("resume_enabled", False)} |
| skipped_count | {stats.get("skipped_count", 0)} |
| processed_count | {stats.get("processed_count", stats.get("total_count", 0))} |
| completed_count | {stats.get("completed_count", 0)} |
| historical_completed_count | {stats.get("historical_completed_count", stats.get("skipped_count", 0))} |
| newly_processed_count | {stats.get("newly_processed_count", stats.get("processed_count", stats.get("total_count", 0)))} |
| current_completed_count | {stats.get("current_completed_count", stats.get("completed_count", 0))} |
| pending_count | {stats.get("pending_count", max(0, stats.get("input_total_count", stats.get("total_count", 0)) - stats.get("completed_count", 0)))} |
| concurrency | {stats.get("concurrency", 1)} |
| concurrency_enabled | {stats.get("concurrency_enabled", False)} |
| parallelized_count | {stats.get("parallelized_count", 0)} |
| keep_rate | {keep_rate:.2%} |
| drop_rate | {drop_rate:.2%} |
| review_rate | {review_rate:.2%} |
| elapsed_seconds | {stats.get("elapsed_seconds", 0)} |

## Issue Distribution

| Issue Type | Count |
| --- | ---: |
{issue_lines}

## Output Files

- clean.jsonl: retained samples
- dropped.jsonl: filtered samples
- review.jsonl: samples requiring manual review
- metrics.json: summary statistics
- operator_logs.jsonl: operator-level execution logs
"""
    path.write_text(content, encoding="utf-8")
