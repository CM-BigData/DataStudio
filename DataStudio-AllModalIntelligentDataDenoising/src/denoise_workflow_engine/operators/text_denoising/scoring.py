from typing import Any
from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

class TextQualityScorer(TextOperator):
    operator_name: str = "text_quality_scorer"  # Operator identifier used by workflow configs and the registry.

    PENALTIES: dict[str, float] = {  # Penalty table that maps issue tags to quality-score deductions.
        "empty_text": 1.0,
        "too_short": 0.35,
        "too_long": 0.15,
        "high_repetition": 0.45,
        "low_info_density": 0.35,
        "sensitive_risk": 0.65,
        "operator_failed": 0.45,
        "invalid_json": 0.7,
        "encoding_low_confidence": 0.15,
        "possible_mojibake": 0.25,
        "language_unknown": 0.15,
        "language_mismatch": 0.45,
        "semantic_low_quality": 0.45,
        "semantic_needs_review": 0.2,
        "semantic_repairable": 0.0,
        "text_repaired": 0.0,
        "llm_api_fallback": 0.0,
    }

    def process(self, item: dict) -> dict:
        """Compute the final quality score for one text sample.

        Business logic:
            1. Start from a full score and subtract configured issue penalties.
            2. Optionally cap the score with semantic-quality output.
            3. Store the final text and generic quality scores on the sample.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out text processing.
            return item
        score = 1.0
        for issue in item.get("issues", []):  # Apply penalties for every recorded issue.
            score -= self.PENALTIES.get(issue, 0.03)
        semantic_score = item.get("metrics", {}).get("semantic_quality_score")
        if semantic_score is not None:  # Cap the score when semantic quality is available.
            try:
                score = min(score, float(semantic_score))
            except (TypeError, ValueError):
                pass
        score = max(0.0, min(1.0, score))
        self.set_metric(item, "text_quality_score", round(score, 4))
        self.set_metric(item, "quality_score", round(score, 4))
        item["quality_score"] = round(score, 4)
        return item
