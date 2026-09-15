from __future__ import annotations

from quality_eval.utilities.text.shared import *  # noqa: F403


class TextConsecutivePunctuationEvalOperator(BaseOperator):
    operator_name: str = "text_consecutive_punctuation_eval"  # Registered operator name used to detect repeated or abnormal consecutive punctuation in text.
    repeated_punctuation_chars: str = r"""!?.,;:，。！？；：、…~～"""
    allowed_mixed_sequences: tuple[str, ...] = ("?!", "!?", "！？", "？！", "!？", "！?", "!!!", "???", "！！", "？？", "……")

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect repeated or abnormal consecutive punctuation inside text.

        Business logic:
            1. Read the sample text and write default metrics when the text is empty.
            2. Scan every consecutive punctuation run and classify it as allowed or abnormal.
            3. Respect configurable repeat thresholds and a configurable allowlist for mixed sequences.
            4. Write summary metrics and append `consecutive_punctuation_abnormal` when abnormal runs exist.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with consecutive-punctuation metrics and issues written back.

        Examples:
            >>> sample = {"payload": {"text": "Really??"}, "metrics": {}, "issues": []}
            >>> TextConsecutivePunctuationEvalOperator({}).process(sample)["metrics"]["consecutive_punctuation_ok"]
            True
        """
        text = _text_value(item)
        if not text:
            self.metric(item, "consecutive_punctuation_ok", True)
            self.metric(item, "consecutive_punctuation_count", 0)
            self.metric(item, "consecutive_punctuation_abnormal_count", 0)
            self.metric(item, "consecutive_punctuation_max_run", 0)
            return item

        sequences = self._find_punctuation_sequences(text)
        abnormal_sequences = [sequence for sequence in sequences if self._is_abnormal_sequence(sequence)]
        max_run = max((len(sequence) for sequence in sequences), default=0)

        self.metric(item, "consecutive_punctuation_ok", len(abnormal_sequences) == 0)
        self.metric(item, "consecutive_punctuation_count", len(sequences))
        self.metric(item, "consecutive_punctuation_abnormal_count", len(abnormal_sequences))
        self.metric(item, "consecutive_punctuation_max_run", max_run)
        if abnormal_sequences:
            self.add_issue(item, "consecutive_punctuation_abnormal")
        return item

    def _find_punctuation_sequences(self, text: str) -> list[str]:
        """Extract consecutive punctuation sequences from text.

        Business logic:
            1. Build a punctuation-only character class from the configured repeated punctuation set.
            2. Match only runs with length two or more so isolated punctuation is ignored.
            3. Return the matched runs in source order for downstream classification.

        Args:
            text (str): Text to inspect.

        Returns:
            list[str]: Consecutive punctuation runs.

        Examples:
            >>> TextConsecutivePunctuationEvalOperator({})._find_punctuation_sequences("Hi?! ok...")
            ['?!', '...']
        """
        pattern = rf"[{re.escape(self._repeated_chars())}]{{2,}}"
        return re.findall(pattern, text)

    def _is_abnormal_sequence(self, sequence: str) -> bool:
        """Classify one punctuation run as allowed or abnormal.

        Business logic:
            1. Accept explicitly allowlisted mixed sequences first.
            2. Accept repeated ellipsis runs when the configured limit is not exceeded.
            3. Accept repeated same-character runs only when they stay within the configured per-character limit.
            4. Treat all other mixed or over-limit runs as abnormal.

        Args:
            sequence (str): Consecutive punctuation run.

        Returns:
            bool: Returns True when the sequence should be reported as abnormal.

        Examples:
            >>> TextConsecutivePunctuationEvalOperator({"rules": {"max_question_exclamation_repeat": 2}})._is_abnormal_sequence("？！")
            False
        """
        if sequence in self._allowed_mixed_sequences():
            return False
        if self._is_ellipsis_sequence(sequence):
            return len(sequence) > self._max_ellipsis_repeat()
        if len(set(sequence)) == 1:
            return len(sequence) > self._max_repeat_for_char(sequence[0])
        return True

    def _is_ellipsis_sequence(self, sequence: str) -> bool:
        """Check whether a punctuation run is an ellipsis-style sequence.

        Business logic:
            1. Treat repeated ASCII dots as one ellipsis family.
            2. Treat repeated Chinese ellipsis marks as another ellipsis family.
            3. Return False for all other punctuation runs.

        Args:
            sequence (str): Consecutive punctuation run.

        Returns:
            bool: Returns True when the run is an ellipsis-style sequence.

        Examples:
            >>> TextConsecutivePunctuationEvalOperator({})._is_ellipsis_sequence("……")
            True
        """
        return set(sequence) == {"…"}

    def _repeated_chars(self) -> str:
        """Return the punctuation character set that participates in run detection.

        Business logic:
            1. Read the configured character set from workflow rules when present.
            2. Fall back to the built-in repeated punctuation character list.
            3. Return a plain string for regex escaping and matching.

        Args:
            None.

        Returns:
            str: Punctuation character set used in run detection.

        Examples:
            >>> "!" in TextConsecutivePunctuationEvalOperator({})._repeated_chars()
            True
        """
        configured = self.rules.get("consecutive_punctuation_chars", self.repeated_punctuation_chars)
        return str(configured)

    def _allowed_mixed_sequences(self) -> set[str]:
        """Return the allowlist for mixed consecutive punctuation runs.

        Business logic:
            1. Read workflow-provided allowlisted sequences when present.
            2. Fall back to the built-in common question/exclamation and ellipsis combinations.
            3. Normalize all sequences to strings for comparison.

        Args:
            None.

        Returns:
            set[str]: Allowlisted punctuation runs.

        Examples:
            >>> "?!?" in TextConsecutivePunctuationEvalOperator({"rules": {"allowed_mixed_punctuation_sequences": ["?!?"]}})._allowed_mixed_sequences()
            True
        """
        configured = self.rules.get("allowed_mixed_punctuation_sequences", self.allowed_mixed_sequences)
        return {str(value) for value in configured}

    def _max_ellipsis_repeat(self) -> int:
        """Return the maximum allowed ellipsis-style run length.

        Business logic:
            1. Read a workflow-specific ellipsis threshold when present.
            2. Fall back to six characters so both `...` and `......` remain allowed.
            3. Return the threshold as an integer.

        Args:
            None.

        Returns:
            int: Maximum allowed ellipsis-style run length.

        Examples:
            >>> TextConsecutivePunctuationEvalOperator({})._max_ellipsis_repeat()
            6
        """
        return int(self.rules.get("max_ellipsis_repeat", 6))

    def _max_repeat_for_char(self, char: str) -> int:
        """Return the maximum allowed repeat count for one punctuation character.

        Business logic:
            1. Use a dedicated threshold for question and exclamation marks when configured.
            2. Use a dedicated threshold for repeated periods when configured.
            3. Fall back to the generic consecutive punctuation repeat threshold for all other punctuation.

        Args:
            char (str): Repeated punctuation character.

        Returns:
            int: Maximum allowed repeat count for the given character.

        Examples:
            >>> TextConsecutivePunctuationEvalOperator({"rules": {"max_consecutive_punctuation_repeat": 2}})._max_repeat_for_char(",")
            2
        """
        if char in {"?", "!", "？", "！"}:
            return int(self.rules.get("max_question_exclamation_repeat", self.rules.get("max_consecutive_punctuation_repeat", 2)))
        if char == ".":
            return int(self.rules.get("max_period_repeat", 3))
        return int(self.rules.get("max_consecutive_punctuation_repeat", 2))
