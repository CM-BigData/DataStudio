from __future__ import annotations

from collections import Counter
from typing import Dict, Iterable

from synthesis_engine.models import GenerationItem


def collect_metrics(items: Iterable[GenerationItem]) -> Dict[str, object]:
    """Aggregate metrics for generated samples

    Business logic:
        1. Materialize the input iterator as a list
        2. Count task types, actions, and issue types
        3. Compute average quality and diversity scores

    Args:
        items (Iterable[GenerationItem]): Sample collection to summarize.

    Returns:
        Dict[str, object]: Aggregated metrics dictionary.

    Examples:
        >>> collect_metrics([])['total']
        0
    """
    item_list = list(items)
    return {
        "total": len(item_list),
        "by_task_type": dict(Counter(item.task_type for item in item_list)),
        "by_action": dict(Counter(item.action for item in item_list)),
        "issues": dict(Counter(issue.get("type", "unknown") for item in item_list for issue in item.issues)),
        "avg_quality_score": _avg([float(item.metrics.get("quality_score", 0)) for item in item_list]),
        "avg_diversity_score": _avg([float(item.metrics.get("diversity_score", 0)) for item in item_list]),
    }


def _avg(values: list[float]) -> float:
    """Compute the average of floating-point values

    Business logic:
        1. Check whether the input is empty
        2. Return 0.0 for an empty list
        3. Otherwise compute the mean and keep four decimal places

    Args:
        values (list[float]): Numeric values to average.

    Returns:
        float: Mean rounded to four decimal places.

    Examples:
        >>> _avg([1.0, 0.0])
        0.5
    """
    return round(sum(values) / len(values), 4) if values else 0.0
