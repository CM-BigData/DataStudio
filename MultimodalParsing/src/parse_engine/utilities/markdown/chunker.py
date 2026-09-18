from __future__ import annotations

from typing import Any, Dict, List, Tuple

import regex


class BaseChunker:
    chunker_name: str = "base_chunker"  # Chunker name: stable business identifier for the chunker.
    chunker_version: str = "1.0.0"  # Chunker version: current implementation version of the chunker.

    def __init__(self, config: Dict[str, Any] | None = None) -> None:
        """Initialize chunker configuration.

        Business logic:
            1. Accept chunking parameters passed by the caller.
            2. Normalize empty input to an empty dictionary.
            3. Store the configuration for concrete chunkers to read.

        Args:
            config: Chunker configuration parameters. May be empty.

        Returns:
            None: The constructor only initializes instance state.

        Examples:
            >>> BaseChunker({"target_len": 1500}).config["target_len"]
            1500"""
        self.config = config or {}  # Chunker config: initialization parameters that control chunker behavior.

    def chunk(self, text: str) -> List[str]:
        """Split text into a list of chunks.

        Business logic:
            1. Define the chunking entrypoint that every chunker must implement.
            2. Accept standard string input.
            3. Raise NotImplementedError in the base class to prevent misuse.

        Args:
            text: Text content to split.

        Returns:
            List[str]: List of chunk texts after splitting.

        Examples:
            >>> hasattr(BaseChunker, "chunk")
            True"""
        raise NotImplementedError


class MarkdownChunker(BaseChunker):
    chunker_name: str = "markdown_chunker"  # Chunker name: stable business identifier for the Markdown chunker.
    chunker_version: str = "1.0.0"  # Chunker version: current implementation version of the Markdown chunker.

    def chunk(self, text: str) -> List[str]:
        """Split Markdown text into chunks.

        Business logic:
            1. Clean newlines, spaces, and overly long separators in Markdown.
            2. Split Markdown into plain-text parts and table parts.
            3. Build chunks by sentence, newline, and table length without breaking semantics.

        Args:
            text: Markdown text to split.

        Returns:
            List[str]: List of Markdown chunks after splitting.

        Examples:
            >>> MarkdownChunker({"target_len": 10}).chunk("First sentence. Second sentence.")[0]
            'First sentence.'"""
        target_len = int(self.config.get("target_len", 1500))
        markdown = self.clean_text(text)
        parts = self.extract_parts(markdown)

        sentences: list[str] = []
        for part_type, content in parts:  # Part dispatch: use different splitting strategies for tables and plain text.
            if not content.strip():  # Empty part: skip Markdown segments that become empty after cleaning.
                continue
            if part_type == "table":  # Table part: keep the header and split by target length.
                sentences.extend(self.table_to_sentences(content, target_len))
            else:
                sentences.extend(self.text_to_sentences(content))

        return self._merge_sentences(sentences, target_len)

    def clean_text(self, markdown: str) -> str:
        """Clean basic Markdown formatting noise.

        Business logic:
            1. Normalize cross-platform line endings to LF.
            2. Merge repeated spaces and compress overly long dashes.
            3. Compress three or more consecutive newlines into two.

        Args:
            markdown: Raw Markdown text.

        Returns:
            str: Cleaned Markdown text.

        Examples:
            >>> MarkdownChunker().clean_text("a\\r\\n\\r\\nb")
            'a\\n\\nb'"""
        cleaned = markdown.replace("\r\n", "\n").replace("\r", "\n")
        cleaned = regex.sub(r" {2,}", " ", cleaned)
        cleaned = regex.sub(r"-{4,}", "---", cleaned)
        cleaned = regex.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    def text_to_sentences(self, text: str) -> List[str]:
        """Split plain text into sentences by Chinese punctuation and newlines.

        Business logic:
            1. Split on Chinese periods, question marks, exclamation marks, and newlines while keeping separators.
            2. Append separators back to the current sentence to preserve semantic boundaries.
            3. Filter empty strings and return the sentence list.

        Args:
            text: Plain Markdown text fragment.

        Returns:
            List[str]: Sentence list split along semantic boundaries.

        Examples:
            >>> MarkdownChunker().text_to_sentences("A。B？")
            ['A。', 'B？']"""
        segments = regex.split(r"([。！？]|(?:\r\n)|\r|\n)", text)
        result: list[str] = []
        buffer = ""
        for segment in segments:  # Segment scan: append separators back to the current sentence.
            buffer += segment
            if segment in ["。", "！", "？", "\n", "\r", "\r\n"]:  # Sentence boundary: Chinese punctuation and newlines both end the current sentence.
                if buffer:  # Non-empty sentence: avoid producing empty chunks.
                    result.append(buffer)
                buffer = ""
        if buffer:  # Trailing fragment: keep content even without a terminator.
            result.append(buffer)
        return [sentence for sentence in result if sentence != ""]

    def table_to_sentences(self, table: str, max_len: int = 1000) -> List[str]:
        """Split a Markdown table into fragments while preserving headers.

        Business logic:
            1. Return the table as one fragment when it stays within the maximum length.
            2. Split content without a standard header/separator row by fixed line groups.
            3. For oversized standard tables, include the header and separator row in every fragment.

        Args:
            table: Markdown table text.
            max_len: Target maximum length for each table fragment.

        Returns:
            List[str]: List of table fragments.

        Examples:
            >>> MarkdownChunker().table_to_sentences("| A |\\n| --- |", 100)[0].startswith("| A |")
            True"""
        if len(table) <= max_len:  # Short table: keep it intact without splitting.
            return [table]

        rows = table.strip().split("\n")
        if len(rows) < 2:  # Non-standard table: split by row batches when there is no header separator line.
            return ["\n".join(rows[index : index + 50]) for index in range(0, len(rows), 50)]

        header = rows[0] + "\n" + rows[1]
        body = rows[2:]
        sentences: list[str] = []
        current = header
        for row in body:  # Body scan: fill the current table chunk row by row.
            if len(current) + len(row) <= max_len:  # Within limit: continue appending to the current table chunk.
                current += "\n" + row
            else:
                sentences.append(current + "\n")
                current = header + "\n" + row
        if current.strip():  # Trailing table: emit the last chunk after the loop.
            sentences.append(current + "\n")
        return sentences

    def extract_parts(self, markdown: str) -> List[Tuple[str, str]]:
        """Split Markdown into plain-text parts and table parts.

        Business logic:
            1. Scan Markdown content line by line.
            2. Recognize consecutive pipe-prefixed lines as table fragments.
            3. Flush buffers when switching between text and tables while preserving original order.

        Args:
            markdown: Cleaned Markdown text.

        Returns:
            List[Tuple[str, str]]: text/table fragments in original order.

        Examples:
            >>> MarkdownChunker().extract_parts("| A |\\n| --- |")[0][0]
            'table'"""
        lines = markdown.splitlines(keepends=True)
        parts: list[tuple[str, str]] = []
        table_buffer: list[str] = []
        text_buffer: list[str] = []
        in_table = False

        def flush_table() -> None:
            """Flush the current table buffer.

            Business logic:
                1. Check whether the table buffer contains any lines.
                2. Join buffered lines into table text with standard newline endings.
                3. Append the result to parts and reset table-scanning state.

            Args:
                None.

            Returns:
                None: Directly mutates the outer buffer variables.

            Examples:
                >>> callable(flush_table)
                True"""
            nonlocal table_buffer, in_table
            if table_buffer:  # Non-empty table buffer: emit one complete table part.
                table_content = "".join(line.rstrip("\r\n") + "\n" for line in table_buffer)
                parts.append(("table", table_content))
                table_buffer = []
                in_table = False

        for line in lines:  # Markdown line scan: recognize text and tables in original order.
            if line.strip().startswith("|"):  # Table line: enter or continue the table buffer.
                if text_buffer:  # Non-empty text buffer: emit the text part before switching to a table.
                    parts.append(("text", "".join(text_buffer)))
                    text_buffer = []
                table_buffer.append(line)
                in_table = True
            else:
                if in_table:  # Table end: flush the table buffer when a non-table line appears.
                    flush_table()
                text_buffer.append(line)

        if text_buffer:  # Trailing text: keep the last text segment after the scan ends.
            parts.append(("text", "".join(text_buffer)))
        flush_table()
        return parts

    def _merge_sentences(self, sentences: List[str], target_len: int) -> List[str]:
        """Merge sentences into chunks within the target length.

        Business logic:
            1. Fill the current chunk buffer sentence by sentence.
            2. Keep merging consecutive sentences while the target length is not exceeded.
            3. Emit the current chunk and start a new one when the limit is exceeded.

        Args:
            sentences: Text fragments already split along semantic boundaries.
            target_len: Target maximum chunk length.

        Returns:
            List[str]: Merged chunk list.

        Examples:
            >>> MarkdownChunker()._merge_sentences(["A.", "B."], 10)
            ['A. B.']"""
        chunks: list[str] = []
        buffer = ""
        for sentence in sentences:  # Sentence merge: fill the chunk buffer in order.
            if not buffer:  # Empty buffer: current sentence becomes the starting point of a new chunk.
                buffer = sentence
            elif len(buffer) + len(sentence) <= target_len:  # Within target length: merge into the current chunk.
                if buffer.endswith(("\n", "\r\n")):  # Newline ending: concatenate directly to avoid an extra space.
                    buffer += sentence
                else:
                    buffer += " " + sentence
            else:
                chunks.append(buffer)
                buffer = sentence
        if buffer:  # Trailing chunk: emit any remaining content after the loop.
            chunks.append(buffer)
        return chunks
