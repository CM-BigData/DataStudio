from quality_eval.utilities.text.shared import *  # noqa: F403

class UnicodeQualityEvalOperator(BaseOperator):
    operator_name: str = "unicode_quality_eval"  # Registered operator name used to detect abnormal-character ratios in text.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect the abnormal-character ratio in text.

        Business logic:
            1. Read the text from `payload.text`.
            2. Record 0 and skip issue detection when the text is empty.
            3. Count abnormal characters and write `abnormal_char_ratio`.
            4. Append the `abnormal_chars` issue when the ratio exceeds the configured threshold.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with abnormal-character metrics and issues written back.

        Examples:
            >>> sample = {"payload": {"text": "normal"}, "metrics": {}, "issues": []}
            >>> UnicodeQualityEvalOperator({}).process(sample)["metrics"]["abnormal_char_ratio"]
            0.0
        """
        text = _text_value(item)
        if not text:  # Missing or empty text is handled by completeness operators, so only the default metric is recorded here.
            self.metric(item, "abnormal_char_ratio", 0)
            return item
        abnormal = sum(1 for char in text if _is_abnormal_char(char))
        ratio = abnormal / max(len(text), 1)
        self.metric(item, "abnormal_char_ratio", round(ratio, 4))
        if ratio > float(self.rules.get("abnormal_char_ratio", 0.3)):  # Treat the sample as dirty text when the abnormal ratio exceeds the threshold.
            self.add_issue(item, "abnormal_chars")
        return item
