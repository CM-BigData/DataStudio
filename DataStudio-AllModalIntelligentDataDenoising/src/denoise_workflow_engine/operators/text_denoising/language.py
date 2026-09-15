from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

from lingua import Language, LanguageDetectorBuilder

class LanguageDetectOperator(TextOperator):
    operator_name: str = "language_detect"  # Operator identifier used by workflow configs and the registry.

    DETECTOR: Any = LanguageDetectorBuilder.from_languages(Language.CHINESE, Language.ENGLISH).build()  # Built-in language detector limited to Chinese and English to avoid external dependencies.

    def process(self, item: dict) -> dict:
        """Detect the language of one text sample.

        Business logic:
            1. Detect language, confidence, and score distribution.
            2. Record language metrics on the sample.
            3. Add issues for unknown, low-confidence, or disallowed languages.

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
        text = self.get_text(item)
        language, confidence, distribution = self._detect(text)
        self.set_metric(item, "language", language)
        self.set_metric(item, "language_confidence", round(confidence, 4))
        self.set_metric(item, "language_distribution", distribution)

        allowed = set(self.config.get("allowed_languages", ["zh", "mixed"]))
        min_confidence = float(self.config.get("min_confidence", 0.25))
        if language == "unknown" or confidence < min_confidence:  # Flag language uncertainty when confidence is too low.
            self.add_issue(item, "language_unknown")
        elif language not in allowed:
            self.add_issue(item, "language_mismatch")
        return item

    def _detect(self, text: str) -> tuple[str, float, dict[str, float]]:
        """Identify the language of the given text.

        Business logic:
            1. Count Chinese, Latin, and numeric characters.
            2. Compute language confidences with the built-in detector.
            3. Return the chosen language together with confidence and score distribution.

        Args:
                text (str): Input text content.

        Returns:
            tuple[str, float, dict[str, float]]: Language label, confidence score, and confidence distribution.

        Examples:
            >>> _detect
            _detect
        """
        chinese = count_chinese_chars(text)
        latin = len(re.findall(r"[A-Za-z]", text))
        digit = len(re.findall(r"\d", text))
        alpha = chinese + latin
        if alpha == 0:  # Fall back to unknown when no alphabetic evidence is available.
            return "unknown", 0.0, {"zh": 0.0, "en": 0.0, "digit": 0.0, "method": "lingua"}
        digit_ratio = digit / max(len(text), 1)
        confidences = {Language.CHINESE: 0.0, Language.ENGLISH: 0.0}
        for value in self.DETECTOR.compute_language_confidence_values(text):  # Collect Chinese and English confidences from the local detector.
            if value.language in confidences:  # Keep only the languages this workflow supports.
                confidences[value.language] = float(value.value)
        zh_confidence = confidences[Language.CHINESE]
        en_confidence = confidences[Language.ENGLISH]
        confidence = max(zh_confidence, en_confidence)
        if alpha < int(self.config.get("min_alpha_chars", 4)) or confidence < float(self.config.get("min_lingua_confidence", 0.45)):  # Mark results as unknown when the detector signal is too weak.
            language = "unknown"
        elif chinese > 0 and latin > 0 and min(zh_confidence, en_confidence) >= float(self.config.get("mixed_min_confidence", 0.12)):
            language = "mixed"
            confidence = max(zh_confidence, en_confidence)
        elif zh_confidence >= en_confidence:
            language = "zh"
        else:
            language = "en"
        return language, confidence, {
            "zh": round(zh_confidence, 4),
            "en": round(en_confidence, 4),
            "digit": round(digit_ratio, 4),
            "method": "lingua",
        }
