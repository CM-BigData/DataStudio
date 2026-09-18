from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable

from parse_engine.models import DataItem


def collect_metrics(items: Iterable[DataItem]) -> Dict[str, object]:
    """Aggregate workflow result metrics.

    Business logic:
        1. Materialize the input iterator into a list so it can be counted multiple times.
        2. Count sample modalities, actions, artifact types, and issue types separately.
        3. Return a JSON-serializable summary metrics dictionary.

    Args:
        items: Iterable of data items after workflow processing has finished.

    Returns:
        Dict[str, object]: Metrics dictionary containing total, by_modality, by_action, artifacts, and issues.

    Examples:
        >>> collect_metrics([])["total"]
        0"""
    item_list = list(items)
    modality_counter = Counter(item.modality for item in item_list)
    action_counter = Counter(item.action for item in item_list)
    artifact_counter = Counter()
    issue_counter = Counter()

    for item in item_list:  # Metric aggregation: count artifact types and issue types for each sample.
        artifact_counter.update(artifact.type for artifact in item.artifacts)
        issue_counter.update(issue.get("type", "unknown") for issue in item.issues)

    return {
        "total": len(item_list),
        "by_modality": dict(modality_counter),
        "by_action": dict(action_counter),
        "artifacts": dict(artifact_counter),
        "issues": dict(issue_counter),
    }
