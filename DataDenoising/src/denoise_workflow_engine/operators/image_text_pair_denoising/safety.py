from typing import Any
from denoise_workflow_engine.utilities.image_text_pair.base import *  # noqa: F403

class PairSafetyFusionOperator(BaseOperator):
    operator_name: str = "pair_safety_fusion"  # Operator identifier used by workflow configs and the registry.

    DEFAULT_HARD_RISK: set[str] = {  # Hard-risk issues that force the pair safety score to zero.
        "sensitive_risk",
        "safety_risk",
        "qrcode_detected",
        "image_missing",
        "decode_failed",
        "pair_missing_image",
        "pair_missing_text",
    }

    def process(self, item: dict) -> dict:
        """Fuse pair-level safety signals for one image-text sample.

        Business logic:
            1. Skip non-pair modalities.
            2. Intersect current issues with the hard-risk issue set.
            3. Record pair-safety metrics and add a pair-safety issue when risk exists.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if item.get("modality") != "image_text_pair":  # Run this operator only for image-text-pair samples.
            return item
        hard_risk = set(self.config.get("hard_risk_issues", [])) or self.DEFAULT_HARD_RISK
        issues = set(item.get("issues", []))
        hits = sorted(issues & hard_risk)
        score = 1.0
        if hits:  # Record pair-level safety risk when any hard-risk issue is present.
            score = 0.0
            self.add_issue(item, "pair_safety_risk")
        self.set_metric(item, "pair_safety_score", round(score, 4))
        self.set_metric(item, "pair_safety_hits", hits)
        return item
