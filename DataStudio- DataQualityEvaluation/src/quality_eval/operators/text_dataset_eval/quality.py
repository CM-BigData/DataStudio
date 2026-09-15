from quality_eval.utilities.text.shared import *  # noqa: F403

class LowQualityTextEvalOperator(BaseOperator):
    operator_name: str = "low_quality_text_eval"  # Registered operator name used to detect repeated characters and repeated fragments in text.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect low-quality repetition patterns inside text.

        Business logic:
            1. Read the sample text and record only a default repetition ratio for empty text.
            2. Compute the share of the most frequent character after removing whitespace.
            3. Use a regular expression to detect repeated 2-to-8-character fragments.
            4. Append `high_repetition` when the single-character ratio exceeds the threshold or repeated fragments exist.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with repetition metrics and issues written back.

        Examples:
            >>> sample = {"payload": {"text": "aaaaaaaa"}, "metrics": {}, "issues": []}
            >>> LowQualityTextEvalOperator({}).process(sample)["issues"]
            ['high_repetition']
        """
        text = _text_value(item)
        if not text:  # Empty text is handled by completeness operators, so this operator only fills the default repetition metric.
            self.metric(item, "repetition_ratio", 0)
            return item
        chars = [char for char in text if not char.isspace()]
        most_common = Counter(chars).most_common(1)
        repetition_ratio = most_common[0][1] / len(chars) if chars and most_common else 0
        repeated_ngram = bool(re.search(r"(.{2,8})\1{3,}", text))
        self.metric(item, "repetition_ratio", round(repetition_ratio, 4))
        if repetition_ratio >= float(self.rules.get("max_single_char_ratio", 0.6)) or repeated_ngram:  # High-frequency characters or repeated fragments both indicate templated dirty text.
            self.add_issue(item, "high_repetition")
        return item

class TextDupRateOperator(BaseOperator):
    operator_name: str = "text_dup_rate"  # Registered operator name used to detect duplicate text across samples.

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        """Build the duplicate-text detection index.

        Business logic:
            1. Initialize the duplicate sample-ID set for the current task.
            2. Normalize each sample's text as the duplicate-detection key.
            3. Add first-seen text to the index and mark both sample IDs when it appears again.
            4. Write duplicate IDs into task context for summary reporting.

        Args:
            items (list[dict[str, Any]]): All text samples in this workflow run.
            context (dict[str, Any]): Context shared across operators.

        Returns:
            None: Writes directly to the instance duplicate set and shared context.

        Examples:
            >>> op = TextDupRateOperator({})
            >>> op.setup([], {})
            >>> op.duplicates
            set()
        """
        self.duplicates: set[str] = set()  # Duplicate sample-ID set used by `process` to mark `duplicate_text`.
        seen: dict[str, str] = {}
        for item in items:  # Cross-sample duplicates can only be identified from a full-sample index.
            text = _normalize_text(_text_value(item))
            if not text:  # Empty text has no stable duplicate semantics, so it is handled by the `empty_text` issue instead.
                continue
            if text in seen:  # When the current text already appeared, both the current and first sample should be marked as duplicates.
                self.duplicates.add(item["id"])
                self.duplicates.add(seen[text])
            else:
                seen[text] = item["id"]
        context["text_duplicate_ids"] = sorted(self.duplicates)

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Mark whether one sample is duplicate text.

        Business logic:
            1. Look up the current sample in the duplicate-ID set built during setup.
            2. Write the `is_duplicate` metric.
            3. Append the `duplicate_text` issue for duplicate samples.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with duplicate metrics and issues written back.

        Examples:
            >>> op = TextDupRateOperator({})
            >>> op.duplicates = {"1"}
            >>> op.process({"id": "1", "metrics": {}, "issues": []})["issues"]
            ['duplicate_text']
        """
        is_duplicate = item.get("id") in self.duplicates
        self.metric(item, "is_duplicate", is_duplicate)
        if is_duplicate:  # Append a sample-level issue when the full-sample index already confirmed duplication.
            self.add_issue(item, "duplicate_text")
        return item

class LabelCompletenessOperator(BaseOperator):
    operator_name: str = "label_completeness"  # Registered operator name used to independently inspect text-label completeness.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check whether a text sample has a complete label.

        Business logic:
            1. Read the label from `meta.label` first and fall back to `payload.label` when missing.
            2. Record the boolean metric `label_complete`.
            3. Append `missing_label` when the label is missing or blank.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with label-completeness metrics and issues written back.

        Examples:
            >>> sample = {"payload": {}, "meta": {}, "metrics": {}, "issues": []}
            >>> LabelCompletenessOperator({}).process(sample)["issues"]
            ['missing_label']
        """
        label = item.get("meta", {}).get("label", item.get("payload", {}).get("label"))
        complete = label is not None and str(label).strip() != ""
        self.metric(item, "label_complete", complete)
        if not complete:  # Missing labels affect supervised evaluation-data usability.
            self.add_issue(item, "missing_label")
        return item


class TextPunctuationPairingEvalOperator(BaseOperator):
    operator_name: str = "text_punctuation_pairing_eval"  # Registered operator name used to detect unmatched or mismatched paired punctuation in text.
    opening_to_closing: dict[str, str] = {
        "(": ")",
        "[": "]",
        "{": "}",
        "（": "）",
        "【": "】",
        "《": "》",
        "“": "”",
        "‘": "’",
    }  # Explicit opening-to-closing mapping used for stack-based pairing checks.
    closing_to_opening: dict[str, str] = {closing: opening for opening, closing in opening_to_closing.items()}  # Reverse mapping used when a closing mark appears first or mismatches the stack top.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect unmatched or mismatched paired punctuation inside text.

        Business logic:
            1. Read the sample text and return default metrics when the text is empty.
            2. Use a stack to validate directional Chinese quotes, book-title marks, and paired brackets.
            3. Handle straight quotes conservatively so common apostrophes or contractions are not over-reported.
            4. Write pairing metrics and append `punctuation_pairing_abnormal` when mismatches or unpaired marks exist.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with punctuation-pairing metrics and issues written back.

        Examples:
            >>> sample = {"payload": {"text": "(title [note])"}, "metrics": {}, "issues": []}
            >>> TextPunctuationPairingEvalOperator({}).process(sample)["metrics"]["punctuation_pairing_ok"]
            True
        """
        text = _text_value(item)
        if not text:  # Empty text is handled by completeness operators, so this operator only fills default metrics.
            self.metric(item, "punctuation_pairing_ok", True)
            self.metric(item, "unpaired_punctuation_count", 0)
            self.metric(item, "mismatched_punctuation_count", 0)
            return item

        unpaired_count, mismatched_count = self._count_pairing_errors(text)
        pairing_ok = unpaired_count == 0 and mismatched_count == 0
        self.metric(item, "punctuation_pairing_ok", pairing_ok)
        self.metric(item, "unpaired_punctuation_count", unpaired_count)
        self.metric(item, "mismatched_punctuation_count", mismatched_count)
        if not pairing_ok:  # Any unpaired or mismatched paired punctuation should be surfaced as a quality issue.
            self.add_issue(item, "punctuation_pairing_abnormal")
        return item

    def _count_pairing_errors(self, text: str) -> tuple[int, int]:
        """Count unpaired and mismatched punctuation errors in text.

        Business logic:
            1. Traverse the text once and maintain a stack for directional paired punctuation.
            2. Count mismatches when a closing mark does not match the latest opening mark.
            3. Track straight single and double quotes with conservative heuristics to avoid common false positives.

        Args:
            text (str): Text to inspect.

        Returns:
            tuple[int, int]: Unpaired count and mismatched count.

        Examples:
            >>> TextPunctuationPairingEvalOperator({})._count_pairing_errors("（test")
            (1, 0)
        """
        stack: list[str] = []
        unpaired_count = 0
        mismatched_count = 0
        double_quote_open = False
        single_quote_open = False

        for index, char in enumerate(text):  # Inspect paired punctuation one character at a time while preserving nesting order.
            if char in self.opening_to_closing:
                stack.append(char)
                continue
            if char in self.closing_to_opening:
                expected_open = self.closing_to_opening[char]
                if not stack:
                    unpaired_count += 1
                elif stack[-1] == expected_open:
                    stack.pop()
                else:
                    mismatched_count += 1
                    stack.pop()
                continue
            if char == '"':
                if self._is_quote_boundary(text, index, '"'):
                    double_quote_open = not double_quote_open
                continue
            if char == "'":
                if self._is_apostrophe(text, index):
                    continue
                if self._is_quote_boundary(text, index, "'"):
                    single_quote_open = not single_quote_open

        if double_quote_open:
            unpaired_count += 1
        if single_quote_open:
            unpaired_count += 1
        unpaired_count += len(stack)
        return unpaired_count, mismatched_count

    def _is_quote_boundary(self, text: str, index: int, mark: str) -> bool:
        """Decide whether a straight quote should participate in pairing checks.

        Business logic:
            1. Read the previous and next characters around the quote mark.
            2. Ignore quote marks embedded in alphanumeric tokens when they look non-structural.
            3. Treat remaining straight quotes as structural boundaries for conservative pairing.

        Args:
            text (str): Full text under inspection.
            index (int): Current quote index.
            mark (str): Quote character, either `'` or `"`.

        Returns:
            bool: Whether the mark should toggle quote pairing state.

        Examples:
            >>> TextPunctuationPairingEvalOperator({})._is_quote_boundary('say \"hi\"', 4, '\"')
            True
        """
        previous_char = text[index - 1] if index > 0 else ""
        next_char = text[index + 1] if index + 1 < len(text) else ""
        if previous_char.isalnum() and next_char.isalnum():  # Skip straight quotes embedded in token-like content.
            return False
        return True

    def _is_apostrophe(self, text: str, index: int) -> bool:
        """Check whether a straight single quote behaves like an apostrophe.

        Business logic:
            1. Read neighboring characters around the single quote.
            2. Treat it as an apostrophe when both neighbors are alphanumeric.
            3. Exclude apostrophes from quote-pairing logic to reduce false positives.

        Args:
            text (str): Full text under inspection.
            index (int): Current single-quote index.

        Returns:
            bool: Whether the mark is functioning as an apostrophe.

        Examples:
            >>> TextPunctuationPairingEvalOperator({})._is_apostrophe(\"don't\", 3)
            True
        """
        previous_char = text[index - 1] if index > 0 else ""
        next_char = text[index + 1] if index + 1 < len(text) else ""
        return previous_char.isalnum() and next_char.isalnum()
