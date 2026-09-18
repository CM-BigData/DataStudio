from typing import Any
from denoise_workflow_engine.utilities.image_text_pair.base import *  # noqa: F403

class PairQualityScorer(BaseOperator):
    operator_name: str = "pair_quality_scorer"  # Operator identifier used by workflow configs and the registry.

    PENALTIES: dict[str, float] = {  # Penalty table that maps issue tags to quality-score deductions.
        "image_text_mismatch": 0.18,
        "ocr_text_mismatch": 0.12,
        "ocr_key_field_conflict": 0.5,
        "clip_mismatch": 0.5,
        "vlm_inconsistent": 0.25,
        "vlm_contradiction": 0.8,
        "pair_safety_risk": 1.0,
        "sensitive_risk": 0.65,
        "safety_risk": 0.9,
        "qrcode_detected": 0.85,
        "watermark_detected": 0.2,
        "logo_detected": 0.2,
        "pair_missing_image": 1.0,
        "pair_missing_text": 1.0,
        "image_missing": 1.0,
        "decode_failed": 1.0,
    }

    def process(self, item: dict) -> dict:
        """Compute the final quality score for one image-text-pair sample.

        Business logic:
            1. Fuse text, image, OCR, similarity, and safety metrics.
            2. Apply issue-based penalties to the fused score.
            3. Store the final pair-level quality score on the sample.

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

        metrics = item.setdefault("metrics", {})
        text_score = metric_or_default(metrics, "text_quality_score", metric_or_default(metrics, "quality_score", 1.0))
        image_score = metric_or_default(metrics, "image_quality_score", metric_or_default(metrics, "quality_score", 1.0))
        keyword_score = metric_or_default(metrics, "image_text_similarity_score", 0.5)
        clip_score = metric_or_default(metrics, "clip_similarity_score", keyword_score)
        ocr_score = metric_or_default(metrics, "ocr_consistency_score", 0.5)
        ocr_key_score = metric_or_default(metrics, "ocr_key_field_consistency_score", 0.5)
        vlm_score = metric_or_default(metrics, "vlm_consistency_score", clip_score)
        safety_score = metric_or_default(metrics, "pair_safety_score", 1.0)
        structure_score = self._structure_score(item)
        pair_score = (
            text_score * 0.16
            + image_score * 0.16
            + keyword_score * 0.14
            + clip_score * 0.18
            + ocr_score * 0.08
            + ocr_key_score * 0.10
            + vlm_score * 0.10
            + safety_score * 0.06
            + structure_score * 0.08
        )
        for issue in item.get("issues", []):  # Apply penalties for every recorded issue.
            pair_score -= self.PENALTIES.get(issue, 0.0)
        pair_score = max(0.0, min(1.0, pair_score))
        metrics["pair_quality_score"] = round(pair_score, 4)
        metrics["quality_score"] = round(pair_score, 4)
        item["quality_score"] = round(pair_score, 4)
        return item

    def _structure_score(self, item: dict) -> float:
        """Compute a binary structural score for pair completeness.

        Business logic:
            1. Read the sample issue list.
            2. Check whether any blocking structural issues are present.
            3. Return 0.0 when blocked, otherwise 1.0.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            float: Structural score.

        Examples:
            >>> _structure_score
            _structure_score
        """
        blocking = {"pair_missing_image", "pair_missing_text", "image_missing", "decode_failed", "empty_text"}
        return 0.0 if blocking & set(item.get("issues", [])) else 1.0
