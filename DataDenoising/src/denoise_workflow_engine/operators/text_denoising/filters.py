from typing import Any
from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

class TextLengthFilter(TextOperator):
    operator_name: str = "text_length_filter"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Filter text by minimum and maximum length constraints.

        Business logic:
            1. Measure the current text length.
            2. Record the length metric.
            3. Add issues when the text is empty, too short, or too long.

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
        text_len = len(self.get_text(item))
        min_length = int(self.config.get("min_length", 20))
        max_length = int(self.config.get("max_length", 20000))
        self.set_metric(item, "text_length", text_len)
        if text_len == 0:  # Treat zero-length text as a direct low-quality case.
            self.add_issue(item, "empty_text")
        elif text_len < min_length:
            self.add_issue(item, "too_short")
        elif text_len > max_length:
            self.add_issue(item, "too_long")
        return item

class RepetitionFilter(TextOperator):
    operator_name: str = "repetition_filter"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect excessive repetition in one text sample.

        Business logic:
            1. Compute repetition scores with several heuristics.
            2. Record the maximum repetition ratio as a metric.
            3. Add an issue when repetition exceeds the configured threshold.

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
        ratio = self._max_char_run_ratio(text)
        ngram_ratio = self._ngram_repetition_ratio(text)
        substring_ratio = self._substring_repetition_ratio(text)
        repetition_ratio = max(ratio, ngram_ratio, substring_ratio)
        self.set_metric(item, "repetition_ratio", round(repetition_ratio, 4))
        if repetition_ratio > float(self.config.get("max_repetition_ratio", 0.35)):  # Flag a quality issue when the ratio exceeds the configured threshold.
            self.add_issue(item, "high_repetition")
        return item

    def _max_char_run_ratio(self, text: str) -> float:
        """Compute the maximum repeated-character run ratio.

        Business logic:
            1. Read the input text.
            2. Find the longest contiguous repeated-character segment.
            3. Return its ratio relative to text length.

        Args:
                text (str): Input text content.

        Returns:
            float: Computed repetition ratio.

        Examples:
            >>> _max_char_run_ratio
            _max_char_run_ratio
        """
        if not text:  # Treat empty text as a degenerate case.
            return 1.0
        max_run = 1
        current = 1
        last = text[0]
        for ch in text[1:]:  # Scan from the second character onward.
            if ch == last:  # Extend the repeated-character run.
                current += 1
            else:
                max_run = max(max_run, current)
                current = 1
                last = ch
        max_run = max(max_run, current)
        return max_run / max(len(text), 1)

    def _ngram_repetition_ratio(self, text: str) -> float:
        """Compute a repetition ratio from repeated tri-grams.

        Business logic:
            1. Tokenize the text.
            2. Build tri-grams across the token sequence.
            3. Return the duplicate ratio among all tri-grams.

        Args:
                text (str): Input text content.

        Returns:
            float: Computed repetition ratio.

        Examples:
            >>> _ngram_repetition_ratio
            _ngram_repetition_ratio
        """
        tokens = re.findall(r"[\w\u4e00-\u9fff]+", text.lower())
        if len(tokens) < 6:  # Short token sequences do not provide stable n-gram repetition signals.
            return 0.0
        ngrams = [" ".join(tokens[i : i + 3]) for i in range(len(tokens) - 2)]
        unique = len(set(ngrams))
        return 1.0 - unique / max(len(ngrams), 1)

    def _substring_repetition_ratio(self, text: str) -> float:
        """Compute a repetition ratio from repeated compact substrings.

        Business logic:
            1. Remove punctuation and whitespace to compact the text.
            2. Scan multiple chunk sizes for repeated substring patterns.
            3. Return the best repetition ratio found.

        Args:
                text (str): Input text content.

        Returns:
            float: Computed repetition ratio.

        Examples:
            >>> _substring_repetition_ratio
            _substring_repetition_ratio
        """
        compact = re.sub(r"[\s,，。.!！?？;；:：、]+", "", text)
        if len(compact) < 8:  # Very short compact text cannot support reliable substring repetition checks.
            return 0.0
        best = 0.0
        max_unit = min(12, max(2, len(compact) // 2))
        for unit_size in range(1, max_unit + 1):  # Scan multiple chunk sizes to catch phrase-level repetition.
            chunks = [compact[i : i + unit_size] for i in range(0, len(compact), unit_size)]
            full_chunks = [chunk for chunk in chunks if len(chunk) == unit_size]
            if len(full_chunks) < 3:  # Require enough full chunks to make the ratio meaningful.
                continue
            most_common = max(full_chunks.count(chunk) for chunk in set(full_chunks))
            ratio = most_common / max(len(full_chunks), 1)
            best = max(best, ratio)
        return best

class LowInfoDensityFilter(TextOperator):
    operator_name: str = "low_info_density_filter"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect text with low information density.

        Business logic:
            1. Estimate useful-character density and uniqueness.
            2. Record both metrics on the sample.
            3. Add an issue when either metric falls below the configured threshold.

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
        useful_chars = re.findall(r"[\w\u4e00-\u9fff]", text)
        density = len(useful_chars) / max(len(text), 1)
        unique_ratio = len(set(useful_chars)) / max(len(useful_chars), 1)
        self.set_metric(item, "info_density", round(density, 4))
        self.set_metric(item, "unique_char_ratio", round(unique_ratio, 4))
        if density < float(self.config.get("min_info_density", 0.35)) or unique_ratio < float(
            self.config.get("min_unique_char_ratio", 0.08)
        ):
            self.add_issue(item, "low_info_density")
        return item
