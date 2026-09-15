from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.base import BaseOperator
from parse_engine.utilities.markdown.chunk import MarkdownChunkArtifactBuilder


class MarkdownChunkOperator(BaseOperator):
    operator_name = "markdown_chunk"  # Operator name: registry name for the Markdown chunking operator used in workflows.

    def process(self, item: DataItem) -> DataItem:
        """Split an intermediate Markdown artifact into chunk artifacts.

        Business logic:
            1. Prefer reading Markdown text from item.intermediate["markdown"].
            2. Fall back to the last markdown artifact when the intermediate value is missing.
            3. Call MarkdownChunker and write the results into markdown_chunk artifacts and metrics.

        Args:
            item: Data item that already contains intermediate Markdown or markdown artifacts.

        Returns:
            DataItem: Data item with markdown_chunk artifacts appended.

        Examples:
            >>> MarkdownChunkOperator({}).operator_name
            'markdown_chunk'"""
        builder = MarkdownChunkArtifactBuilder(self.config)
        markdown = builder.resolve_markdown(item)
        if not markdown.strip():  # Empty Markdown: no content can be chunked, so record an issue and pass through.
            item.issues.append({"type": "empty_markdown_chunks", "message": "Markdown content is empty for chunking"})
            item.metrics["chunk_count"] = 0
            item.metrics["chunk_target_len"] = int(self.config.get("target_len", 1500))
            return item

        chunk_artifacts = builder.build_chunk_artifacts(item, markdown, self.operator_name)
        item.artifacts.extend(chunk_artifacts)
        target_len = int(builder.chunker.config.get("target_len", 1500))
        total = len(chunk_artifacts)
        item.metrics["chunk_count"] = total
        item.metrics["chunk_target_len"] = target_len
        if total == 0:  # Unexpected empty result: input was non-empty but the algorithm produced no chunks.
            item.issues.append({"type": "empty_markdown_chunks", "message": "Markdown chunker produced no chunks"})
        return item
