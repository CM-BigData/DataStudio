from __future__ import annotations
from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


class QualityGateOperator(BaseOperator):
    operator_name: str = "quality_gate"  # Operator identifier used by workflow configs and the registry.

    DEFAULT_HARD_FAIL: set[str] = {  # Hard-fail issue tags that force the sample to be dropped regardless of score.
        "empty_text",
        "image_missing",
        "decode_failed",
        "invalid_json",
    }
    DEFAULT_REVIEW_ISSUES: set[str] = set()  # Review-only issue tags that should be routed to manual review without forcing a drop.

    def process(self, item: dict) -> dict:
        """Decide the final action for a sample based on issues and quality score.

        Business logic:
            1. Read the configured hard-fail issue set and the sample score.
            2. Apply keep and review thresholds when no hard-fail issue is present.
            3. Write the final action back to the sample in place.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        hard_fail = set(self.config.get("hard_fail_issues", [])) or self.DEFAULT_HARD_FAIL
        review_issues = set(self.config.get("review_issues", [])) or self.DEFAULT_REVIEW_ISSUES
        issues = set(item.get("issues", []))
        score = float(item.get("quality_score", item.get("metrics", {}).get("quality_score", 1.0)))
        keep_score = float(self.config.get("keep_score", 0.75))
        review_score = float(self.config.get("review_score", 0.55))

        if issues & hard_fail:  # Hard-fail issues always force a drop decision.
            item["action"] = "drop"
        elif issues & review_issues:  # Review-only issues override score-based keep decisions.
            item["action"] = "review"
        elif score >= keep_score:
            item["action"] = "keep"
        elif score >= review_score:
            item["action"] = "review"
        else:
            item["action"] = "drop"
        return item
