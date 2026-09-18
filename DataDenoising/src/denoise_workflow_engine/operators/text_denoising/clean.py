from typing import Any
from denoise_workflow_engine.utilities.text.base import *  # noqa: F403

class HTMLCleanOperator(TextOperator):
    operator_name: str = "html_clean"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Clean HTML, scripts, styles, and link noise from one sample.

        Business logic:
            1. Read the current text payload.
            2. Remove HTML tags, scripts, styles, and plain links.
            3. Write cleaned text back and record an issue when the text changes.

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
        cleaned = html.unescape(text)
        cleaned = re.sub(r"<script[\s\S]*?</script>", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"<style[\s\S]*?</style>", " ", cleaned, flags=re.I)
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)
        cleaned = re.sub(r"https?://\S+|www\.\S+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned != text:  # Record cleanup only when the text actually changes.
            self.add_issue(item, "html_or_url_removed")
        self.set_text(item, cleaned)
        return item

class MarkdownCleanOperator(TextOperator):
    operator_name: str = "markdown_clean"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Clean Markdown formatting noise from one sample.

        Business logic:
            1. Read the current text payload.
            2. Remove Markdown fences, inline markup, and quoting markers.
            3. Write cleaned text back and record an issue when the text changes.

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
        cleaned = text
        cleaned = re.sub(r"```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = cleaned.replace("```", "")
        cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\(\s*", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        cleaned = re.sub(r"(?m)^\s{0,3}#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"(?m)^\s*[-*_]{3,}\s*$", " ", cleaned)
        cleaned = re.sub(r"(?m)^\s*>+\s?", "", cleaned)
        cleaned = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned != text:  # Record cleanup only when the text actually changes.
            self.add_issue(item, "markdown_noise_removed")
        self.set_text(item, cleaned)
        return item
