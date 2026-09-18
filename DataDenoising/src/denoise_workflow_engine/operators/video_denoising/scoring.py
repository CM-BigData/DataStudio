from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403

class VideoQualityScorer(VideoOperator):
    operator_name: str = "video_quality_scorer"  # Operator identifier used by workflow configs and the registry.

    PENALTIES: dict[str, float] = {  # Penalty table that maps issue tags to quality-score deductions.
        "video_missing": 1.0,
        "unsupported_video_format": 0.35,
        "video_too_small": 0.7,
        "ffprobe_failed": 0.8,
        "no_video_stream": 1.0,
        "decode_failed": 1.0,
        "video_too_short": 0.45,
        "video_too_long": 0.2,
        "low_video_resolution": 0.35,
        "low_fps": 0.25,
        "keyframe_extract_failed": 0.35,
        "black_frames": 0.65,
        "blurry_video": 0.45,
        "pure_video_frames": 0.6,
        "video_under_exposure": 0.35,
        "video_over_exposure": 0.35,
        "video_high_noise": 0.3,
        "freeze_frames": 0.65,
        "video_qrcode_detected": 0.85,
        "video_safety_risk": 0.9,
        "audio_missing": 0.15,
        "audio_extract_failed": 0.15,
        "silent_audio": 0.35,
        "low_audio_volume": 0.2,
        "audio_visual_inconsistent": 0.4,
        "speech_subtitle_inconsistent": 0.35,
        "sensitive_speech_text": 0.8,
        "subtitle_ocr_api_fallback": 0.0,
        "asr_api_fallback": 0.0,
        "vlm_video_api_fallback": 0.0,
        "video_repaired": 0.0,
        "video_repair_failed": 0.25,
    }

    def process(self, item: dict) -> dict:
        """Compute the final quality score for one video sample.

        Business logic:
            1. Start from a full score and subtract configured issue penalties.
            2. Optionally cap the score with video safety output.
            3. Store the final video and generic quality scores on the sample.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out video processing.
            return item
        score = 1.0
        for issue in item.get("issues", []):  # Apply penalties for every recorded issue.
            score -= self.PENALTIES.get(issue, 0.0)
        safety_score = item.get("metrics", {}).get("video_safety_score")
        if safety_score is not None:  # Cap the score when safety output is available.
            try:
                score = min(score, float(safety_score))
            except (TypeError, ValueError):
                pass
        score = max(0.0, min(1.0, score))
        self.set_metric(item, "video_quality_score", round(score, 4))
        self.set_metric(item, "quality_score", round(score, 4))
        item["quality_score"] = round(score, 4)
        return item
