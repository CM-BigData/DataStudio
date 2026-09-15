from __future__ import annotations

import unicodedata

from quality_eval.utilities.text.shared import *  # noqa: F403


class TextSpecialCharactersEvalOperator(BaseOperator):
    operator_name: str = "text_special_characters_eval"  # Registered operator name used to detect control characters, invisible marks, and mojibake remnants in text.
    default_allowed_controls: tuple[str, ...] = ("\n", "\r", "\t")
    default_invisible_chars: tuple[str, ...] = (
        "\u200b",  # Zero width space.
        "\u200c",  # Zero width non-joiner.
        "\u200d",  # Zero width joiner.
        "\ufeff",  # Byte order mark.
        "\u2060",  # Word joiner.
        "\u00ad",  # Soft hyphen.
    )
    default_mojibake_fragments: tuple[str, ...] = (
        "ï»¿",
        "â€™",
        "â€œ",
        "â€\x9d",
        "â€¦",
        "Â",
        "Ã",
        "¤",
        "�",
    )

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect control characters, invisible characters, and mojibake remnants inside text.

        Business logic:
            1. Read the sample text and write default metrics when the text is empty.
            2. Scan characters to count disallowed control characters and invisible characters.
            3. Scan text fragments to count mojibake-remnant hits.
            4. Write summary metrics and append `special_characters_abnormal` when any abnormal marker exists.

        Args:
            item (dict[str, Any]): Text sample.

        Returns:
            dict[str, Any]: Sample with special-character metrics and issues written back.

        Examples:
            >>> sample = {"payload": {"text": "hello\\u200bworld"}, "metrics": {}, "issues": []}
            >>> TextSpecialCharactersEvalOperator({}).process(sample)["metrics"]["special_characters_ok"]
            False
        """
        text = _text_value(item)
        if not text:
            self.metric(item, "special_characters_ok", True)
            self.metric(item, "special_character_count", 0)
            self.metric(item, "control_character_count", 0)
            self.metric(item, "invisible_character_count", 0)
            self.metric(item, "mojibake_fragment_count", 0)
            return item

        control_count, invisible_count = self._count_abnormal_chars(text)
        mojibake_count = self._count_mojibake_fragments(text)
        total_count = control_count + invisible_count + mojibake_count

        self.metric(item, "special_characters_ok", total_count == 0)
        self.metric(item, "special_character_count", total_count)
        self.metric(item, "control_character_count", control_count)
        self.metric(item, "invisible_character_count", invisible_count)
        self.metric(item, "mojibake_fragment_count", mojibake_count)
        if total_count > 0:
            self.add_issue(item, "special_characters_abnormal")
        return item

    def _count_abnormal_chars(self, text: str) -> tuple[int, int]:
        """Count disallowed control characters and invisible characters.

        Business logic:
            1. Traverse the text character by character.
            2. Count configured invisible characters directly.
            3. Count control/format characters only when they are not on the allowlist.
            4. Return both counters for metric reporting.

        Args:
            text (str): Text to inspect.

        Returns:
            tuple[int, int]: Control-character count and invisible-character count.

        Examples:
            >>> TextSpecialCharactersEvalOperator({})._count_abnormal_chars("a\\u200bb")
            (0, 1)
        """
        control_count = 0
        invisible_count = 0
        invisible_chars = self._invisible_chars()
        allowed_controls = self._allowed_controls()

        for char in text:
            if char in invisible_chars:
                invisible_count += 1
                continue
            category = unicodedata.category(char)
            if char in allowed_controls:
                continue
            if category == "Cc":
                control_count += 1
                continue
            if category == "Cf":
                invisible_count += 1
        return control_count, invisible_count

    def _count_mojibake_fragments(self, text: str) -> int:
        """Count mojibake-like residue fragments inside text.

        Business logic:
            1. Read the configured mojibake-fragment allowlist.
            2. Count every fragment occurrence in the text.
            3. Return the total fragment-hit count for metrics and issue decisions.

        Args:
            text (str): Text to inspect.

        Returns:
            int: Mojibake-fragment occurrence count.

        Examples:
            >>> TextSpecialCharactersEvalOperator({})._count_mojibake_fragments("ï»¿Title")
            1
        """
        return sum(text.count(fragment) for fragment in self._mojibake_fragments())

    def _allowed_controls(self) -> set[str]:
        """Return the allowlist for harmless control characters.

        Business logic:
            1. Read workflow-provided allowed control characters when present.
            2. Fall back to newline, carriage return, and tab.
            3. Normalize values into a set for fast membership checks.

        Args:
            None.

        Returns:
            set[str]: Allowed control characters.

        Examples:
            >>> "\\n" in TextSpecialCharactersEvalOperator({})._allowed_controls()
            True
        """
        configured = self.rules.get("allowed_control_characters", self.default_allowed_controls)
        return {str(value) for value in configured}

    def _invisible_chars(self) -> set[str]:
        """Return the configured invisible-character denylist.

        Business logic:
            1. Read workflow-provided invisible characters when present.
            2. Fall back to common zero-width and hidden formatting characters.
            3. Normalize values into a set for fast membership checks.

        Args:
            None.

        Returns:
            set[str]: Invisible characters to flag.

        Examples:
            >>> "\\u200b" in TextSpecialCharactersEvalOperator({})._invisible_chars()
            True
        """
        configured = self.rules.get("invisible_characters", self.default_invisible_chars)
        return {str(value) for value in configured}

    def _mojibake_fragments(self) -> tuple[str, ...]:
        """Return mojibake-remnant fragments that should be flagged.

        Business logic:
            1. Read workflow-provided mojibake fragments when present.
            2. Fall back to common UTF-8/Latin-1 corruption residues and replacement glyphs.
            3. Preserve order for deterministic counting and debugging.

        Args:
            None.

        Returns:
            tuple[str, ...]: Mojibake-remnant fragments to scan.

        Examples:
            >>> "Â" in TextSpecialCharactersEvalOperator({})._mojibake_fragments()
            True
        """
        configured = self.rules.get("mojibake_fragments", self.default_mojibake_fragments)
        return tuple(str(value) for value in configured)
