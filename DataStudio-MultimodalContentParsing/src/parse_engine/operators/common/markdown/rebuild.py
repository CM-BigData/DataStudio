from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.utilities.markdown.rebuild import MarkdownArtifactRebuilder


class MarkdownRebuildOperator(BaseOperator):
    operator_name = "markdown_rebuild"  # Operator name: registry name for the Markdown reconstruction step.

    def process(self, item: DataItem) -> DataItem:
        """Rebuild parsing artifacts into Markdown text.

        Business logic:
            1. Return immediately when the sample has no artifacts.
            2. Convert headings to Markdown titles by heading_level when present, tables to Markdown tables, and plain text to direct content blocks.
            3. Generate a markdown artifact and cache it in item.intermediate["markdown"].

        Args:
            item: Data item that already contains parsing artifacts.

        Returns:
            DataItem: Data item with the markdown artifact appended.

        Examples:
            >>> MarkdownRebuildOperator({}).operator_name
            'markdown_rebuild'"""
        if not item.artifacts:  # No upstream artifacts: there is no Markdown content to rebuild.
            return item

        rebuilder = MarkdownArtifactRebuilder()
        markdown = rebuilder.rebuild_markdown(item)
        item.intermediate["markdown"] = markdown
        if markdown:  # Rebuilt content exists: append a markdown artifact for downstream use.
            item.artifacts.append(rebuilder.build_markdown_artifact(item, markdown, self.operator_name))
        return item
