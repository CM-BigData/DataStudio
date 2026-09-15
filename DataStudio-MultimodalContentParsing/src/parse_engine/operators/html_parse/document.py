from __future__ import annotations

from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup, Tag

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class HtmlBodyExtractOperator(BaseOperator):
    operator_name = "html_body_extract"  # Operator name: registry name for the HTML body extraction step.

    def process(self, item: DataItem) -> DataItem:
        """Extract the HTML body and convert it into structured artifacts.

        Business logic:
            1. Only process samples with html modality and return other samples unchanged.
            2. Read HTML, remove script/style/nav noise, and prefer body or StartFragment content.
            3. Emit heading, paragraph, and table artifacts, then record body metrics and empty issues.

        Args:
            item (DataItem): HTML sample in the current workflow.

        Returns:
            DataItem: Sample with HTML structure artifacts appended.

        Examples:
            >>> HtmlBodyExtractOperator({}).operator_name
            'html_body_extract'
        """
        if item.modality != "html":  # Cross-modality guard: the HTML body operator only handles html samples.
            return item

        html_text = self._read_html(item)
        if not html_text.strip():  # Empty input: record a clear reason for downstream reporting.
            item.action = "failed"
            item.metrics["html_content_length"] = 0
            item.metrics["html_artifact_count"] = 0
            item.issues.append({"type": "empty_html_document", "message": "HTML content is empty"})
            return item

        soup = BeautifulSoup(self._extract_fragment(html_text), "html.parser")
        root = self._prepare_root(soup)

        artifact_index = len(item.artifacts)
        heading_count = 0
        paragraph_count = 0
        table_count = 0
        source_file = item.source.get("path") or item.payload.get("path") or item.id

        for heading in self._iter_headings(root):
            text = self._normalize_text(heading.get_text(" ", strip=True))
            if not text:
                continue
            artifact_index += 1
            heading_count += 1
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_html_heading_{artifact_index}",
                    type="heading",
                    text=text,
                    data={"tag": heading.name, "level": self._heading_level(heading.name)},
                    source_trace=SourceTrace(file=str(source_file), operator=self.operator_name),
                )
            )

        for paragraph in self._iter_paragraphs(root):
            text = self._normalize_text(paragraph.get_text(" ", strip=True))
            if not text:
                continue
            artifact_index += 1
            paragraph_count += 1
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_html_paragraph_{artifact_index}",
                    type="paragraph",
                    text=text,
                    data={"tag": paragraph.name},
                    source_trace=SourceTrace(file=str(source_file), operator=self.operator_name),
                )
            )

        for table in root.find_all("table"):
            rows = self._table_rows(table)
            if not rows:
                continue
            artifact_index += 1
            table_count += 1
            item.artifacts.append(
                Artifact(
                    id=f"{item.id}_html_table_{artifact_index}",
                    type="table",
                    text="\n".join([" | ".join(row) for row in rows]),
                    data={"rows": rows, "tag": "table"},
                    source_trace=SourceTrace(file=str(source_file), operator=self.operator_name),
                )
            )

        item.metrics["html_heading_count"] = heading_count
        item.metrics["html_paragraph_count"] = paragraph_count
        item.metrics["html_table_count"] = table_count
        item.metrics["html_artifact_count"] = heading_count + paragraph_count + table_count
        item.metrics["html_content_length"] = len(html_text)
        item.action = "parsed" if item.artifacts else "failed"
        if item.action == "failed":
            item.issues.append({"type": "empty_html_body", "message": "HTML extraction produced no body content"})
        return item

    def _read_html(self, item: DataItem) -> str:
        """Read the raw HTML source.

        Business logic:
            1. Prefer reading HTML file content from payload.path.
            2. Fall back to payload.text when the file path is missing.
            3. Return an empty string when neither source exists.

        Args:
            item (DataItem): Current HTML sample.

        Returns:
            str: Raw HTML text.

        Examples:
            >>> HtmlBodyExtractOperator({})._read_html(DataItem(id="x", modality="html", source={}, payload={}))
            ''
        """
        path_value = item.payload.get("path")
        if path_value:
            return Path(str(path_value)).read_text(encoding="utf-8")
        text_value = item.payload.get("text")
        return str(text_value) if text_value is not None else ""

    def _extract_fragment(self, html_text: str) -> str:
        """Extract the main HTML fragment.

        Business logic:
            1. Prefer content between StartFragment and EndFragment markers.
            2. Otherwise extract the complete html tag range.
            3. Return the original text when no explicit wrapper exists.

        Args:
            html_text (str): Raw HTML text.

        Returns:
            str: Extracted main fragment text.

        Examples:
            >>> "body" in HtmlBodyExtractOperator({})._extract_fragment("<html><body>x</body></html>")
            True
        """
        start_marker = "<!--StartFragment-->"
        end_marker = "<!--EndFragment-->"
        start = html_text.find(start_marker)
        end = html_text.find(end_marker)
        if start != -1 and end != -1 and start < end:
            return html_text[start + len(start_marker):end]
        html_start = html_text.find("<html")
        html_end = html_text.rfind("</html>")
        if html_start != -1 and html_end != -1 and html_start < html_end:
            return html_text[html_start:html_end + len("</html>")]
        return html_text

    def _prepare_root(self, soup: BeautifulSoup) -> Tag:
        """Remove noise and select the body root node.

        Business logic:
            1. Remove common noise tags such as script, style, nav, footer, and aside.
            2. Prefer the body tag as the content root.
            3. Fall back to the whole soup when body is missing.

        Args:
            soup (BeautifulSoup): Parsed HTML tree.

        Returns:
            Tag: Cleaned content root node.

        Examples:
            >>> HtmlBodyExtractOperator({})._prepare_root(BeautifulSoup("<html><body>x</body></html>", "html.parser")).name
            'body'
        """
        for node in soup.find_all(["script", "style", "nav", "header", "footer", "aside", "noscript", "form", "svg"]):
            node.decompose()
        return soup.body or soup

    def _iter_headings(self, root: Tag) -> Iterable[Tag]:
        """Iterate body heading nodes.

        Business logic:
            1. Find h1 through h6 nodes in document order.
            2. Preserve the original HTML heading order.
            3. Return an iterator of nodes ready for artifact generation.

        Args:
            root (Tag): Content root node.

        Returns:
            Iterable[Tag]: Heading node sequence.

        Examples:
            >>> len(list(HtmlBodyExtractOperator({})._iter_headings(BeautifulSoup("<h1>a</h1>", "html.parser"))))
            1
        """
        return root.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

    def _iter_paragraphs(self, root: Tag) -> Iterable[Tag]:
        """Iterate body paragraph nodes.

        Business logic:
            1. Use p, li, blockquote, and pre nodes as body text sources.
            2. Skip nodes inside tables to avoid duplicating table artifacts.
            3. Return paragraph nodes in document order.

        Args:
            root (Tag): Content root node.

        Returns:
            Iterable[Tag]: Paragraph node sequence.

        Examples:
            >>> len(list(HtmlBodyExtractOperator({})._iter_paragraphs(BeautifulSoup("<p>a</p>", "html.parser"))))
            1
        """
        for node in root.find_all(["p", "li", "blockquote", "pre"]):
            if node.find_parent("table") is not None:
                continue
            yield node

    def _table_rows(self, table: Tag) -> list[list[str]]:
        """Extract rows and cells from an HTML table.

        Business logic:
            1. Traverse tr nodes and read th/td cell text.
            2. Merge cell line breaks with spaces to reduce noisy splits.
            3. Skip empty rows and return a two-dimensional string array.

        Args:
            table (Tag): Table node.

        Returns:
            list[list[str]]: Table row and cell text.

        Examples:
            >>> HtmlBodyExtractOperator({})._table_rows(BeautifulSoup("<table><tr><td>a</td></tr></table>", "html.parser").table)
            [['a']]
        """
        rows: list[list[str]] = []
        for row in table.find_all("tr"):
            cells = [self._normalize_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            cells = [cell for cell in cells if cell]
            if cells:
                rows.append(cells)
        return rows

    def _normalize_text(self, text: str) -> str:
        """Normalize body text.

        Business logic:
            1. Trim edge whitespace and collapse consecutive whitespace.
            2. Preserve necessary spaces between body words.
            3. Return stable text suitable for artifacts.

        Args:
            text (str): Raw text.

        Returns:
            str: Cleaned body text.

        Examples:
            >>> HtmlBodyExtractOperator({})._normalize_text(" a\\n  b ")
            'a b'
        """
        return " ".join(text.split())

    def _heading_level(self, tag_name: str | None) -> int:
        """Compute the heading level.

        Business logic:
            1. Read the h1-h6 tag name.
            2. Fall back to 2 when parsing fails.
            3. Return an integer heading level for downstream use.

        Args:
            tag_name (str | None): Heading tag name.

        Returns:
            int: Heading level.

        Examples:
            >>> HtmlBodyExtractOperator({})._heading_level("h3")
            3
        """
        if tag_name and len(tag_name) == 2 and tag_name.startswith("h") and tag_name[1].isdigit():
            return int(tag_name[1])
        return 2
