from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from quality_eval.runtime.path_security import safe_output_path
from quality_eval.utilities.schema import ANNOTATION_ISSUES


GB_MAPPING: list[dict[str, str]] = [  # National-standard dimension mapping used to show implemented metric coverage in reports.
    {
        "dimension": "Compliance",
        "dimension_zh": "合规性",
        "implemented_metrics": "schema_valid, format_supported",
        "implemented_metrics_zh": "结构校验、格式支持",
        "status": "enabled",
    },
    {
        "dimension": "Completeness",
        "dimension_zh": "完整性",
        "implemented_metrics": "completeness_score, label_complete",
        "implemented_metrics_zh": "完整性得分、标签完整性",
        "status": "enabled",
    },
    {
        "dimension": "Accuracy",
        "dimension_zh": "准确性",
        "implemented_metrics": "basic readability, bbox boundary rules",
        "implemented_metrics_zh": "基础可读性、标注框边界规则",
        "status": "partially_enabled",
    },
    {
        "dimension": "Consistency",
        "dimension_zh": "一致性",
        "implemented_metrics": "complex annotation consistency",
        "implemented_metrics_zh": "复杂标注一致性",
        "status": "not_enabled",
    },
    {
        "dimension": "Safety",
        "dimension_zh": "安全性",
        "implemented_metrics": "safety model, PII/NSFW model",
        "implemented_metrics_zh": "安全模型、PII/NSFW 模型",
        "status": "not_enabled",
    },
    {
        "dimension": "Cleanliness",
        "dimension_zh": "清洁度",
        "implemented_metrics": "duplicates, abnormal characters, blur, low-quality text",
        "implemented_metrics_zh": "重复样本、异常字符、模糊图像、低质量文本",
        "status": "enabled",
    },
    {
        "dimension": "Diversity",
        "dimension_zh": "多样性",
        "implemented_metrics": "topic coverage, class balance",
        "implemented_metrics_zh": "主题覆盖、类别均衡",
        "status": "not_enabled",
    },
    {
        "dimension": "Model Fitness",
        "dimension_zh": "模型适配性",
        "implemented_metrics": "downstream-task fitness score",
        "implemented_metrics_zh": "下游任务适配得分",
        "status": "not_enabled",
    },
]

ENHANCED_STATUS: dict[str, str] = {  # Enhanced-metric status used to show advanced capabilities that are not enabled yet.
    "application_quality_score": "not_enabled",
    "complex_annotation_consistency": "not_enabled",
    "semantic_duplicate": "not_enabled",
    "caption_image_alignment": "not_enabled",
    "safety_model": "not_enabled",
    "topic_diversity": "not_enabled",
}


def build_summary(
    task_id: str,
    workflow_id: str,
    modality: str,
    results: list[dict[str, Any]],
    elapsed_ms: float,
    paths: dict[str, str],
    operator_logs: list[dict[str, Any]],
    duplicate_ids: list[str] | None = None,
    metrics_snapshot: dict[str, Any] | None = None,
    score_weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build a dataset-level quality summary.

    Business logic:
        1. Summarize sample counts, status distribution, action distribution, level distribution, and issue distribution.
        2. Extract low-quality, high-risk, annotation-problem, and duplicate sample lists.
        3. Compute average quality score, annotation quality score, base quality score, and comprehensive score.
        4. Merge throughput and latency from the executor metrics snapshot.
        5. Return a JSON-serializable summary-report structure.

    Args:
        task_id (str): Current task ID.
        workflow_id (str): Workflow ID.
        modality (str): Data modality.
        results (list[dict[str, Any]]): Sample-level result list.
        elapsed_ms (float): Workflow execution time.
        paths (dict[str, str]): Output-path dictionary.
        operator_logs (list[dict[str, Any]]): Operator audit logs.
        duplicate_ids (list[str] | None, optional): Duplicate sample IDs discovered during setup.
        metrics_snapshot (dict[str, Any] | None, optional): Executor metrics snapshot.
        score_weights (dict[str, float] | None, optional): Dimension weight map for comprehensive scoring.

    Returns:
        dict[str, Any]: Dataset-level summary structure.

    Examples:
        >>> build_summary("t", "w", "text", [], 0, {}, [])["total_count"]
        0
    """
    total = len(results)
    issue_distribution = Counter(issue for item in results for issue in item.get("issues", []))
    level_distribution = Counter(item.get("level", "unknown") for item in results)
    actions = Counter(item.get("action", "pending") for item in results)
    statuses = Counter(item.get("status", "success") for item in results)
    scores = [float(item.get("score", 0)) for item in results]
    abnormal = [item for item in results if item.get("issues")]
    low_quality = sorted(
        [item for item in results if float(item.get("score", 0)) < 60],
        key=lambda item: float(item.get("score", 0)),
    )[:20]
    high_risk = [
        item
        for item in results
        if item.get("action") == "drop" or float(item.get("score", 0)) < 60
    ][:20]
    annotation_problem = [
        item for item in results if ANNOTATION_ISSUES.intersection(set(item.get("issues", [])))
    ][:20]
    quality_score_avg = round(mean(scores), 2) if scores else 0
    annotation_scores = [100 if "missing_label" not in item.get("issues", []) else 0 for item in results]
    annotation_quality_score = round(mean(annotation_scores), 2) if annotation_scores else 0
    dimension_scores = _dimension_scores(results, quality_score_avg, annotation_quality_score)
    base_quality_score = round(mean([dimension_scores[key] for key in ("Compliance", "Completeness", "Cleanliness")]), 2) if results else 0
    comprehensive_score = _weighted_score(dimension_scores, score_weights)
    throughput = (metrics_snapshot or {}).get("throughput_qps")
    if throughput is None:  # Fall back to total sample count and elapsed time when executor throughput is unavailable.
        throughput = round(total / (elapsed_ms / 1000), 4) if elapsed_ms > 0 else total
    avg_latency = (metrics_snapshot or {}).get("avg_latency_ms")
    if avg_latency is None:  # Fall back to operator logs when executor average latency is unavailable.
        avg_latency = round(mean([log["latency_ms"] for log in operator_logs]), 2) if operator_logs else 0
    traceability = _traceability_summary(results, operator_logs, paths)

    return {
        "task_id": task_id,
        "workflow_id": workflow_id,
        "modality": modality,
        "total_count": total,
        "success_count": statuses.get("success", total - statuses.get("failed", 0)),
        "failed_count": statuses.get("failed", 0),
        "drop_count": actions.get("drop", 0),
        "review_count": actions.get("review", 0),
        "valid_count": actions.get("keep", 0),
        "abnormal_count": len(abnormal),
        "avg_latency_ms": avg_latency,
        "throughput_qps": throughput,
        "quality_score_avg": quality_score_avg,
        "base_quality_score": base_quality_score,
        "annotation_quality_score": annotation_quality_score,
        "application_quality_score": None,
        "comprehensive_score": comprehensive_score,
        "dimension_scores": dimension_scores,
        "level_distribution": dict(level_distribution),
        "issue_distribution": dict(issue_distribution),
        "duplicate_sample_ids": duplicate_ids or _ids_with_issue(results, "duplicate_text", "duplicate_image"),
        "low_quality_samples": _compact_samples(low_quality),
        "high_risk_samples": _compact_samples(high_risk),
        "annotation_problem_samples": _compact_samples(annotation_problem),
        "enhanced_metric_status": ENHANCED_STATUS,
        "gb_mapping": GB_MAPPING,
        "rectification_suggestions": _rectification_suggestions(issue_distribution),
        "traceability": traceability,
        "paths": paths,
    }


def write_markdown_report(summary: dict[str, Any], path: Path) -> None:
    """Write summary results as a Markdown report.

    Business logic:
        1. Ensure the report output directory exists.
        2. Assemble Markdown lines from summary using fixed sections.
        3. Render dimensions, levels, issues, sample lists, and suggestions.
        4. Write the report text to the target path.

    Args:
        summary (dict[str, Any]): Dataset-level summary structure.
        path (Path): Markdown report output path.

    Returns:
        None: Writes the Markdown file directly.

    Examples:
        >>> callable(write_markdown_report)
        True
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Data Quality Evaluation Report",
        "",
        f"- Task ID: `{summary['task_id']}`",
        f"- Workflow: `{summary['workflow_id']}`",
        f"- Data modality: `{summary['modality']}`",
        f"- Total samples: {summary.get('input_total_count', summary['total_count'])}",
        f"- Current run samples: {summary.get('newly_processed_count', summary.get('processed_count', summary['total_count']))}",
        f"- Valid samples: {summary['valid_count']}",
        f"- Abnormal samples: {summary['abnormal_count']}",
        f"- resume_enabled: {summary.get('resume_enabled', False)}",
        f"- skipped_count: {summary.get('skipped_count', 0)}",
        f"- processed_count: {summary.get('processed_count', summary['total_count'])}",
        f"- completed_count: {summary.get('completed_count', 0)}",
        f"- Historical completed count: {summary.get('historical_completed_count', summary.get('skipped_count', 0))}",
        f"- Newly processed count: {summary.get('newly_processed_count', summary.get('processed_count', summary['total_count']))}",
        f"- Current completed count: {summary.get('current_completed_count', summary.get('completed_count', 0))}",
        f"- Pending count: {summary.get('pending_count', max(0, summary.get('input_total_count', summary['total_count']) - summary.get('completed_count', 0)))}",
        "",
        "## Traceability",
        "",
        f"- trace_enabled: {summary.get('traceability', {}).get('trace_enabled', False)}",
        f"- trace_coverage: {summary.get('traceability', {}).get('trace_coverage', 0)}",
        f"- traced_sample_count: {summary.get('traceability', {}).get('traced_sample_count', 0)}",
        f"- missing_trace_count: {summary.get('traceability', {}).get('missing_trace_count', 0)}",
        f"- failed_trace_count: {summary.get('traceability', {}).get('failed_trace_count', 0)}",
        f"- trace_event_count: {summary.get('traceability', {}).get('trace_event_count', 0)}",
        f"- trace_log_path: `{summary.get('traceability', {}).get('trace_log_path', summary.get('paths', {}).get('log_path', ''))}`",
        f"- checkpoint_path: `{summary.get('paths', {}).get('checkpoint_path', '')}`",
        f"- error_path: `{summary.get('paths', {}).get('error_path', '')}`",
        "",
        "## Quality Scores",
        "",
        f"- Base quality score: {summary['base_quality_score']}",
        f"- Annotation quality score: {summary['annotation_quality_score']}",
        f"- Application quality score: not_enabled",
        f"- Comprehensive quality score: {summary['comprehensive_score']}",
        "",
        "## Dimension Scores",
        "",
        _markdown_table(["Dimension", "Score"], summary["dimension_scores"].items()),
        "",
        "## Quality Level Distribution",
        "",
        _markdown_table(["Level", "Count"], _level_distribution_rows(summary["level_distribution"])),
        "",
        "## Issue Distribution",
        "",
        _markdown_table(["Issue Code", "Count"], summary["issue_distribution"].items()),
        "",
        "## Duplicate Samples",
        "",
        _markdown_list(summary["duplicate_sample_ids"]),
        "",
        "## Low-Quality Samples",
        "",
        _sample_table(summary["low_quality_samples"]),
        "",
        "## High-Risk Samples",
        "",
        _sample_table(summary["high_risk_samples"]),
        "",
        "## Annotation-Issue Samples",
        "",
        _sample_table(summary["annotation_problem_samples"]),
        "",
        "## Enhanced Metric Status",
        "",
        _markdown_table(["Metric", "Status"], summary["enhanced_metric_status"].items()),
        "",
        "## National Standard Mapping",
        "",
        _markdown_table(
            [
                "Dimension (EN)",
                "Dimension (ZH)",
                "Implemented/Planned Metrics (EN)",
                "Implemented/Planned Metrics (ZH)",
                "Status",
            ],
            [
                (
                    item["dimension"],
                    item.get("dimension_zh", ""),
                    item["implemented_metrics"],
                    item.get("implemented_metrics_zh", ""),
                    item["status"],
                )
                for item in summary["gb_mapping"]
            ],
        ),
        "",
        "## Remediation Suggestions",
        "",
        _markdown_list(summary["rectification_suggestions"]),
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def regenerate_markdown_report(task: Path, output: Path | None = None) -> Path:
    """Regenerate a Markdown report from a summary JSON file.

    Business logic:
        1. Find the first summary JSON file when task is a directory.
        2. Read task directly as the summary JSON when task is a file.
        3. Prefer the command-line-provided output path, otherwise read summary.paths.report_path.
        4. Generate the report with write_markdown_report and return the path.

    Args:
        task (Path): Run directory or summary JSON path.
        output (Path | None, optional): Optional report output path.

    Returns:
        Path: Actual Markdown report path written.

    Examples:
        >>> callable(regenerate_markdown_report)
        True
    """
    summary_path = task
    if task.is_dir():  # export-report accepts a run directory instead of a concrete summary file.
        candidates = sorted(task.glob("*summary*.json"))
        if not candidates:  # Report content cannot be restored when the directory has no summary file.
            raise FileNotFoundError(f"No summary JSON found in {task}")
        summary_path = candidates[0]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if output:
        report_path = safe_output_path(output, name="report output")
    else:
        report_path = safe_output_path(summary["paths"]["report_path"], name="summary report path", base_dir=summary_path.parent)
        summary_dir = summary_path.parent.resolve()
        try:
            report_path.resolve().relative_to(summary_dir)
        except ValueError as exc:
            raise ValueError("summary report path must stay under the summary directory") from exc
    write_markdown_report(summary, report_path)
    return report_path


def _ids_with_issue(results: list[dict[str, Any]], *issues: str) -> list[str]:
    """Filter sample IDs that contain specific issues.

    Business logic:
        1. Convert target issue codes into a set.
        2. Iterate through sample results.
        3. Return sample_id when a sample's issues intersect the target set.

    Args:
        results (list[dict[str, Any]]): Sample result list.
        issues (str): Target issue codes.

    Returns:
        list[str]: Sample IDs that match the target issues.

    Examples:
        >>> _ids_with_issue([{"sample_id": "s", "issues": ["x"]}], "x")
        ['s']
    """
    wanted = set(issues)
    return [item["sample_id"] for item in results if wanted.intersection(item.get("issues", []))]


def _traceability_summary(
    results: list[dict[str, Any]],
    operator_logs: list[dict[str, Any]],
    paths: dict[str, str],
) -> dict[str, Any]:
    """Build the traceability summary.

    Business logic:
        1. Count result samples that contain trace_id and trace data.
        2. Count trace events and failed events in operator logs.
        3. Calculate trace coverage and return the report display structure.

    Args:
        results (list[dict[str, Any]]): Sample-level result list.
        operator_logs (list[dict[str, Any]]): Trace/operator log list.
        paths (dict[str, str]): Output path mapping.

    Returns:
        dict[str, Any]: Traceability summary.

    Examples:
        >>> _traceability_summary([{"trace_id": "t", "trace": [{}]}], [{}], {})["trace_coverage"]
        1.0
    """
    total = len(results)
    traced_results = [
        item
        for item in results
        if item.get("trace_id") and isinstance(item.get("trace"), list) and len(item.get("trace", [])) > 0
    ]
    failed_trace_count = sum(1 for log in operator_logs if log.get("status") == "failed")
    trace_coverage = round(len(traced_results) / total, 4) if total else 0
    return {
        "trace_enabled": bool(traced_results or operator_logs),
        "trace_coverage": trace_coverage,
        "traced_sample_count": len(traced_results),
        "missing_trace_count": total - len(traced_results),
        "failed_trace_count": failed_trace_count,
        "trace_event_count": len(operator_logs),
        "trace_log_path": paths.get("log_path", ""),
    }


def _compact_samples(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compact sample results into report display fields.

    Business logic:
        1. Iterate through the sample result list.
        2. Keep only sample ID, score, level, action, and issues.
        3. Return a compact structure suitable for summary and Markdown display.

    Args:
        items (list[dict[str, Any]]): Sample result list.

    Returns:
        list[dict[str, Any]]: Compact sample list.

    Examples:
        >>> _compact_samples([{"sample_id": "s", "score": 1}])[0]["sample_id"]
        's'
    """
    return [
        {
            "sample_id": item.get("sample_id"),
            "score": item.get("score"),
            "level": item.get("level"),
            "action": item.get("action"),
            "issues": item.get("issues", []),
        }
        for item in items
    ]


def _rectification_suggestions(issue_distribution: Counter[str]) -> list[str]:
    """Generate remediation suggestions from the issue distribution.

    Business logic:
        1. Return a downstream-ready message when there are no issues.
        2. Recommend fixing usability first when schema, path, or empty-content issues appear.
        3. Recommend deduplication when duplicate issues appear.
        4. Recommend manual review when annotation issues appear.
        5. Recommend cleaning or recollection when low-quality content issues appear.

    Args:
        issue_distribution (Counter[str]): Issue-code distribution.

    Returns:
        list[str]: Remediation suggestion list.

    Examples:
        >>> _rectification_suggestions(Counter())[0]
        'No significant quality issues were found. The dataset can proceed to downstream processing.'
    """
    if not issue_distribution:  # Reports should return an explicit positive conclusion when no issue distribution exists.
        return ["No significant quality issues were found. The dataset can proceed to downstream processing."]
    suggestions = []
    if any(issue in issue_distribution for issue in ("empty_text", "missing_text_field", "missing_image_path", "image_not_found")):  # Availability issues directly affect whether samples can be used downstream.
        suggestions.append("Prioritize fixing schema, path, and empty-content issues because they directly affect sample usability.")
    if any(issue in issue_distribution for issue in ("duplicate_text", "duplicate_image")):  # Duplicate samples distort distribution and reduce training efficiency.
        suggestions.append("Deduplicate repeated samples and keep only the most reliable or best-annotated versions.")
    if any(issue in issue_distribution for issue in ("missing_label", "bbox_out_of_bounds")):  # Annotation issues usually require human review or annotation-pipeline fixes.
        suggestions.append("Send samples with missing labels or out-of-bounds bbox annotations to manual review.")
    if any(issue in issue_distribution for issue in ("abnormal_chars", "high_repetition", "blurred_image")):  # Low-quality content usually needs cleaning, removal, or recollection.
        suggestions.append("Clean, remove, or recollect low-quality content.")
    return suggestions


def _dimension_scores(
    results: list[dict[str, Any]],
    quality_score_avg: float,
    annotation_quality_score: float,
) -> dict[str, float]:
    """Calculate national-standard dimension quality scores.

    Business logic:
        1. Count the issue distribution across all samples.
        2. Use the sample total to derive each dimension's deduction ratio.
        3. Calculate compliance, accuracy, and cleanliness from different issue sets.
        4. Reuse the annotation quality score as completeness.
        5. Return None for disabled dimensions to preserve report placeholders.

    Args:
        results (list[dict[str, Any]]): Sample result list.
        quality_score_avg (float): Average sample quality score.
        annotation_quality_score (float): Annotation quality score.

    Returns:
        dict[str, float]: Mapping from dimension name to score or None.

    Examples:
        >>> _dimension_scores([], 0, 0)["Compliance"]
        100
    """
    total = max(len(results), 1)
    issues = Counter(issue for item in results for issue in item.get("issues", []))

    def score_without(issue_codes: set[str]) -> float:
        """Deduct a dimension score by issue set.

        Business logic:
            1. Count sample issue occurrences affected by the given issue set.
            2. Convert the count into a deduction ratio using the total sample count.
            3. Clamp the score at 0 minimum and round to two decimals.

        Args:
            issue_codes (set[str]): Issue-code set that affects a dimension.

        Returns:
            float: Dimension score.

        Examples:
            >>> score_without(set())
            100
        """
        affected = sum(count for issue, count in issues.items() if issue in issue_codes)
        return round(max(0, 100 - affected / total * 100), 2)

    return {
        "Compliance": score_without({"missing_id", "missing_text_field", "unsupported_format", "missing_image_path"}),
        "Completeness": annotation_quality_score,
        "Accuracy": score_without({"image_unreadable", "image_not_found", "bbox_out_of_bounds"}),
        "Consistency": None,
        "Safety": None,
        "Cleanliness": score_without({"duplicate_text", "duplicate_image", "abnormal_chars", "high_repetition", "blurred_image"}),
        "Diversity": None,
        "Model Fitness": None,
        "Average Sample Quality": quality_score_avg,
    }


def _weighted_score(dimension_scores: dict[str, float | None], score_weights: dict[str, float] | None) -> float:
    """Calculate the weighted comprehensive score for enabled dimensions.

    Business logic:
        1. Prepare default national-standard dimension weights.
        2. Override defaults with configured weights.
        3. Include only enabled dimensions whose scores are not None.
        4. Normalize enabled weights before calculating the comprehensive score.

    Args:
        dimension_scores (dict[str, float | None]): Dimension score mapping.
        score_weights (dict[str, float] | None): Optional dimension weights.

    Returns:
        float: Comprehensive quality score.

    Examples:
        >>> _weighted_score({"Compliance": 100}, {"Compliance": 1})
        100.0
    """
    default_weights = {  # Default national-standard weights used when score_weights is not provided in config.
        "Compliance": 0.15,
        "Completeness": 0.15,
        "Accuracy": 0.20,
        "Consistency": 0.15,
        "Safety": 0.15,
        "Cleanliness": 0.10,
        "Diversity": 0.05,
        "Model Fitness": 0.05,
    }
    weights = score_weights or default_weights
    enabled = {
        key: (dimension_scores[key], weight)
        for key, weight in weights.items()
        if key in dimension_scores and dimension_scores[key] is not None
    }
    weight_sum = sum(weight for _, weight in enabled.values())
    if not enabled or weight_sum == 0:  # A comprehensive score cannot be computed when no dimensions are enabled or the total weight is zero.
        return 0
    return round(sum(score * weight for score, weight in enabled.values()) / weight_sum, 2)


def _markdown_table(headers: list[str], rows: Any) -> str:
    """Render a Markdown table.

    Business logic:
        1. Convert rows to a list so emptiness checks and repeated iteration work.
        2. Return "none" when there are no rows.
        3. Write the header and separator rows.
        4. Convert each row value to a string and join the Markdown table.

    Args:
        headers (list[str]): Header list.
        rows (Any): Row data, either tuple lists or other iterables.

    Returns:
        str: Markdown table text.

    Examples:
        >>> _markdown_table(["a"], [("b",)])
        '|a|\\n|---|\\n|b|'
    """
    rows = list(rows)
    if not rows:  # Represent empty tables explicitly instead of producing an empty Markdown table.
        return "none"
    output = ["|" + "|".join(headers) + "|", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:  # Rows may come from dict.items or any custom iterable.
        if not isinstance(row, tuple):  # Normalize non-tuple rows so they can be joined consistently.
            row = tuple(row)
        output.append("|" + "|".join(str(value) for value in row) + "|")
    return "\n".join(output)


def _markdown_list(values: list[Any]) -> str:
    """Render a Markdown list.

    Business logic:
        1. Return "none" when there are no values.
        2. Render each value as a Markdown list item when values exist.
        3. Wrap each value in backticks to highlight sample IDs or codes.

    Args:
        values (list[Any]): Values to render.

    Returns:
        str: Markdown list text.

    Examples:
        >>> _markdown_list(["s1"])
        '- `s1`'
    """
    if not values:  # Represent empty lists explicitly in the report.
        return "none"
    return "\n".join(f"- `{value}`" for value in values)


def _english_level(level: Any) -> str:
    """Normalize quality-level display values to English.

    Business logic:
        1. Translate legacy Chinese level values from older summary files.
        2. Return current English level values unchanged.
        3. Convert unknown values to strings for stable report rendering.

    Args:
        level (Any): Quality level value from a result or summary.

    Returns:
        str: English quality-level display value.

    Examples:
        >>> _english_level("优秀")
        'Excellent'
    """
    mapping = {
        "优秀": "Excellent",
        "良好": "Good",
        "一般": "Average",
        "较差": "Poor",
    }
    return mapping.get(level, str(level))


def _level_distribution_rows(distribution: dict[str, int]) -> list[tuple[str, int]]:
    """Render level distribution rows with English level names.

    Business logic:
        1. Iterate through the summary level distribution.
        2. Normalize each level name to English for report display.
        3. Merge counts that map to the same English level.

    Args:
        distribution (dict[str, int]): Raw level-count mapping.

    Returns:
        list[tuple[str, int]]: English display rows.

    Examples:
        >>> _level_distribution_rows({"优秀": 1})
        [('Excellent', 1)]
    """
    normalized: Counter[str] = Counter()
    for level, count in distribution.items():
        normalized[_english_level(level)] += count
    return list(normalized.items())


def _sample_table(samples: list[dict[str, Any]]) -> str:
    """Render a sample-list table.

    Business logic:
        1. Return "none" when there are no samples.
        2. Extract sample ID, score, level, action, and issues.
        3. Join the issue list with commas.
        4. Reuse the Markdown table renderer for output.

    Args:
        samples (list[dict[str, Any]]): Samples to display.

    Returns:
        str: Markdown sample table.

    Examples:
        >>> _sample_table([])
        'none'
    """
    if not samples:  # Keep the report section while showing that no matching samples exist.
        return "none"
    rows = [
        (
            sample["sample_id"],
            sample["score"],
            _english_level(sample["level"]),
            sample["action"],
            ",".join(sample["issues"]),
        )
        for sample in samples
    ]
    return _markdown_table(["Sample ID", "Score", "Level", "Action", "Issues"], rows)
