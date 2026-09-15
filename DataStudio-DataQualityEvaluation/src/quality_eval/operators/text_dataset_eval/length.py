from quality_eval.utilities.text.shared import *  # noqa: F403

class DatasetSchemaCheckOperator(BaseOperator):
    operator_name: str = "dataset_schema_check"  # Registered operator name used to validate required text-sample fields.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Validate the basic schema of a text sample.

        Business logic:
            1. Check for missing or empty IDs marked during loading.
            2. Check whether the `payload` contains a `text` field.
            3. Write whether the schema is valid to the `schema_valid` metric.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with schema issues and metrics written back.

        Examples:
            >>> sample = {"id": "", "payload": {}, "meta": {}, "issues": [], "metrics": {}}
            >>> DatasetSchemaCheckOperator({}).process(sample)["metrics"]["schema_valid"]
            False
        """
        if item.get("meta", {}).get("_missing_id") or not item.get("id"):  # The loader may synthesize temporary IDs, so the original missing-ID fact must be preserved.
            self.add_issue(item, "missing_id")
        if "text" not in item.get("payload", {}):  # Missing the text field blocks all downstream text-quality checks.
            self.add_issue(item, "missing_text_field")
        self.metric(item, "schema_valid", not {"missing_id", "missing_text_field"}.intersection(item["issues"]))
        return item

class FieldCompletenessOperator(BaseOperator):
    operator_name: str = "field_completeness"  # Registered operator name used to inspect text and label completeness.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Evaluate field completeness for a text sample.

        Business logic:
            1. Check whether the text field is a blank string.
            2. Read the label from `meta.label` or `payload.label`.
            3. Append `missing_label` when the label is missing.
            4. Compute the completeness percentage from ID, text, and label.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with completeness issues and metrics written back.

        Examples:
            >>> sample = {"id": "1", "payload": {"text": "x"}, "meta": {}, "issues": [], "metrics": {}}
            >>> FieldCompletenessOperator({}).process(sample)["metrics"]["completeness_score"]
            66.67
        """
        payload = item.get("payload", {})
        text = payload.get("text")
        if isinstance(text, str) and not text.strip():  # A present-but-blank text field is a content-completeness issue.
            self.add_issue(item, "empty_text")
        label = item.get("meta", {}).get("label", payload.get("label"))
        if label is None or str(label).strip() == "":  # Missing labels reduce the usability of supervised data.
            self.add_issue(item, "missing_label")
        present = 1 if item.get("id") else 0
        present += 1 if "text" in payload and str(payload.get("text", "")).strip() else 0
        present += 1 if label is not None and str(label).strip() else 0
        self.metric(item, "completeness_score", round(present / 3 * 100, 2))
        return item

class TextLengthEvalOperator(BaseOperator):
    operator_name: str = "text_length_eval"  # Registered operator name used to detect text-length threshold issues.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check whether text length falls within configured thresholds.

        Business logic:
            1. Read the sample text and record its character length.
            2. Let completeness operators handle blank text so this operator does not add duplicate length issues.
            3. Append `too_short` when non-empty text is shorter than the minimum threshold.
            4. Append `too_long` when non-empty text exceeds the maximum threshold.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with length metrics and issues written back.

        Examples:
            >>> sample = {"payload": {"text": "abc"}, "metrics": {}, "issues": []}
            >>> TextLengthEvalOperator({"rules": {"min_text_length": 10}}).process(sample)["issues"]
            ['too_short']
        """
        text = _text_value(item)
        length = len(text)
        self.metric(item, "length", length)
        if text.strip():  # Blank text is already covered by completeness issues, so avoid extra `too_short` flags.
            if length < int(self.rules.get("min_text_length", 10)):  # Very short text usually lacks meaningful semantic context.
                self.add_issue(item, "too_short")
            if length > int(self.rules.get("max_text_length", 2000)):  # Very long text may need splitting or truncation before ingestion.
                self.add_issue(item, "too_long")
        return item
