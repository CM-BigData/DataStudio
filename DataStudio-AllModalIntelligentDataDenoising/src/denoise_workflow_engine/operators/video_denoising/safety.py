from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403

class SpeechSubtitleConsistencyOperator(VideoOperator):
    operator_name: str = "speech_subtitle_consistency"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Compare speech and subtitle content consistency for one video sample.

        Business logic:
            1. Read ASR text and subtitle text from intermediate workflow state.
            2. Compute token overlap between speech and subtitle content.
            3. Record the score and add an inconsistency issue when it is too low.

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
        asr_text = str(item.get("intermediate", {}).get("asr_text", "") or "")
        subtitle_text = str(item.get("intermediate", {}).get("subtitle_text", "") or "")
        if not asr_text.strip() or not subtitle_text.strip():  # Skip consistency checks when either ASR or subtitles are empty.
            self.set_metric(item, "speech_subtitle_consistency_score", None)
            return item
        score = token_overlap(asr_text, subtitle_text)
        self.set_metric(item, "speech_subtitle_consistency_score", round(score, 4))
        if score < float(self.config.get("min_consistency", 0.25)):  # Flag inconsistency when overlap falls below the configured threshold.
            self.add_issue(item, "speech_subtitle_inconsistent")
        return item

class AudioVisualConsistencyOperator(VideoOperator):
    operator_name: str = "audio_visual_consistency"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Compare visual keyword hints against audio/text evidence for one video sample.

        Business logic:
            1. Read visual keywords plus ASR and subtitle text.
            2. Compute token overlap between expected visual tokens and available text.
            3. Record the score and add an inconsistency issue when it is too low.

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
        visual_keywords = (
            item.get("intermediate", {}).get("visual_keywords")
            or item.get("payload", {}).get("visual_keywords")
            or item.get("meta", {}).get("visual_keywords")
            or []
        )
        visual_keywords = as_list(visual_keywords)
        text = " ".join(
            [
                str(item.get("intermediate", {}).get("asr_text", "")),
                str(item.get("intermediate", {}).get("subtitle_text", "")),
            ]
        )
        if not visual_keywords or not text.strip():  # Skip consistency checks when visual hints or text evidence are missing.
            self.set_metric(item, "audio_visual_consistency_score", None)
            return item
        expected = normalize_tokens(" ".join(str(token) for token in visual_keywords))
        text_tokens = normalize_tokens(text)
        score = len(expected & text_tokens) / max(len(expected), 1)
        self.set_metric(item, "audio_visual_consistency_score", round(score, 4))
        if score < float(self.config.get("min_consistency", 0.2)):  # Flag inconsistency when overlap falls below the configured threshold.
            self.add_issue(item, "audio_visual_inconsistent")
        return item

class VideoSafetyFusionOperator(VideoOperator):
    operator_name: str = "video_safety_fusion"  # Operator identifier used by workflow configs and the registry.

    SENSITIVE_CATEGORIES: dict[str, list[str]] = {  # Keyword rules mapped by video risk category.
        "gambling": ["赌博", "博彩", "六合彩"],
        "fraud": ["诈骗", "刷单返利", "套现", "杀猪盘"],
        "porn": ["涉黄", "色情", "裸聊"],
        "violence": ["暴恐", "恐怖袭击", "极端组织"],
        "spam": ["点击领取", "加微信", "推广返佣"],
    }
    HARD_RISK: set[str] = {  # Hard-risk issue tags that force the fused safety score to drop.
        "video_missing",
        "decode_failed",
        "no_video_stream",
        "ffprobe_failed",
        "video_qrcode_detected",
        "video_safety_risk",
        "sensitive_speech_text",
    }

    def process(self, item: dict) -> dict:
        """Fuse video-text and issue-based safety signals for one sample.

        Business logic:
            1. Scan ASR and subtitle text for risky keyword categories.
            2. Add issue evidence when risky text is detected.
            3. Compute a conservative fused video safety score from hard-risk issues.

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
        text = " ".join(
            [
                str(item.get("intermediate", {}).get("asr_text", "")),
                str(item.get("intermediate", {}).get("subtitle_text", "")),
            ]
        )
        hits = {}
        for category, keywords in self.SENSITIVE_CATEGORIES.items():  # Scan text against each risk-category keyword list.
            matched = [keyword for keyword in keywords if keyword in text]
            if matched:  # Preserve matched evidence keywords for the current risk category.
                hits[category] = matched
        if hits:  # Record issue evidence when risky keywords are detected.
            self.add_issue(item, "sensitive_speech_text")
            self.set_metric(item, "video_sensitive_categories", hits)
        hard_risk = set(self.config.get("hard_risk_issues", [])) or self.HARD_RISK
        risk_hits = sorted(set(item.get("issues", [])) & hard_risk)
        score = 0.0 if risk_hits else 1.0
        self.set_metric(item, "video_safety_score", round(score, 4))
        self.set_metric(item, "video_safety_hits", risk_hits)
        return item
