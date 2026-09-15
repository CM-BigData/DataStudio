from typing import Any
from denoise_workflow_engine.utilities.image.base import *  # noqa: F403

class ImageQualityScorer(ImageOperator):
    operator_name: str = "image_quality_scorer"  # Operator identifier used by workflow configs and the registry.

    PENALTIES: dict[str, float] = {  # Penalty table that maps issue tags to quality-score deductions.
        "image_missing": 1.0,
        "decode_failed": 1.0,
        "low_resolution": 0.35,
        "abnormal_aspect_ratio": 0.25,
        "blur": 0.35,
        "high_noise": 0.25,
        "under_exposure": 0.3,
        "over_exposure": 0.3,
        "pure_color": 0.5,
        "reference_low_psnr": 0.15,
        "reference_low_ssim": 0.15,
        "reference_severe_difference": 0.55,
        "watermark_detected": 0.35,
        "qrcode_detected": 0.85,
        "logo_detected": 0.3,
        "safety_risk": 0.9,
        "subject_missing": 0.8,
        "subject_weak": 0.25,
        "subject_crop_risk": 0.25,
        "vlm_drop_hint": 0.6,
        "vlm_review_hint": 0.2,
        "vlm_low_quality": 0.45,
        "vlm_quality_review": 0.2,
        "vlm_api_fallback": 0.0,
        "image_repaired": 0.0,
    }

    def process(self, item: dict) -> dict:
        """Compute the final quality score for one image sample.

        Business logic:
            1. Start from a full score and subtract configured issue penalties.
            2. Optionally cap the score with VLM-based quality output.
            3. Store the final image and generic quality scores on the sample.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out image processing.
            return item
        score = 1.0
        for issue in item.get("issues", []):  # Apply penalties for every recorded issue.
            score -= self.PENALTIES.get(issue, 0.0)
        vlm_score = item.get("metrics", {}).get("vlm_image_quality_score")
        if vlm_score is not None:  # Cap the score when VLM output is available.
            try:
                score = min(score, float(vlm_score))
            except (TypeError, ValueError):
                pass
        score = max(0.0, min(1.0, score))
        self.set_metric(item, "image_quality_score", round(score, 4))
        self.set_metric(item, "quality_score", round(score, 4))
        item["quality_score"] = round(score, 4)
        return item
