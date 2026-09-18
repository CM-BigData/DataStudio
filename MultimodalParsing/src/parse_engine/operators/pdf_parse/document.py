from __future__ import annotations

from pathlib import Path

import pdfplumber

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


def _group_chars_into_blocks(page, y_tolerance: float = 2.0, block_gap: float = 5.0):
    """Group page chars into block-line-span hierarchy.

    Args:
        page: pdfplumber Page object.
        y_tolerance: max y-difference for chars to be considered on the same line.
        block_gap: min vertical gap between lines to start a new block.

    Returns:
        List[dict]: blocks with keys type, bbox, lines; each line has bbox, spans;
        each span has text, size.
    """
    chars = page.chars
    if not chars:
        return []

    # Sort by y then x
    chars = sorted(chars, key=lambda c: (c.get("top", 0), c.get("x0", 0)))

    # Group chars into lines by y-proximity
    lines: list[list[dict]] = []
    current_line: list[dict] = []
    current_y = chars[0].get("top", 0) if chars else 0

    for ch in chars:
        y = ch.get("top", 0)
        if abs(y - current_y) > y_tolerance:
            if current_line:
                lines.append(current_line)
            current_line = [ch]
            current_y = y
        else:
            current_line.append(ch)

    if current_line:
        lines.append(current_line)

    # Transform lines into line dicts with spans
    line_dicts = []
    for line_chars in lines:
        # Sort chars within line by x
        line_chars = sorted(line_chars, key=lambda c: (c.get("x0", 0)))
        # Merge consecutive chars with same font size into spans
        spans: list[dict] = []
        current_span_chars: list[dict] = []
        current_size = None
        for ch in line_chars:
            size = round(float(ch.get("size", ch.get("height", 0))), 2)
            if current_size is None or abs(size - current_size) > 0.5:
                if current_span_chars:
                    spans.append({
                        "text": "".join(s.get("text", "") for s in current_span_chars),
                        "size": current_size,
                    })
                current_span_chars = [ch]
                current_size = size
            else:
                current_span_chars.append(ch)
        if current_span_chars:
            spans.append({
                "text": "".join(s.get("text", "") for s in current_span_chars),
                "size": current_size,
            })

        line_bbox = [
            round(float(min(c.get("x0", 0) for c in line_chars)), 2),
            round(float(min(c.get("top", 0) for c in line_chars)), 2),
            round(float(max(c.get("x1", 0) for c in line_chars)), 2),
            round(float(max(c.get("bottom", 0) for c in line_chars)), 2),
        ]
        line_dicts.append({"bbox": line_bbox, "spans": spans})

    # Group lines into blocks by vertical gap
    blocks: list[dict] = []
    current_block_lines: list[dict] = []
    prev_y_bottom = None

    for line in line_dicts:
        y_top = line["bbox"][1]
        if prev_y_bottom is not None and (y_top - prev_y_bottom) > block_gap:
            if current_block_lines:
                blocks.append({"type": 0, "lines": current_block_lines})
            current_block_lines = [line]
        else:
            current_block_lines.append(line)
        prev_y_bottom = line["bbox"][3]

    if current_block_lines:
        blocks.append({"type": 0, "lines": current_block_lines})

    # Compute block bbox from lines
    for block in blocks:
        block_lines = block["lines"]
        block["bbox"] = [
            round(float(min(l["bbox"][0] for l in block_lines)), 2),
            round(float(min(l["bbox"][1] for l in block_lines)), 2),
            round(float(max(l["bbox"][2] for l in block_lines)), 2),
            round(float(max(l["bbox"][3] for l in block_lines)), 2),
        ]

    return blocks


class PdfTextExtractOperator(BaseOperator):
    operator_name = "pdf_text_extract"

    def process(self, item: DataItem) -> DataItem:
        """Extract plain-text artifacts from PDF pages.

        Business logic:
            1. Pass non-PDF samples through unchanged.
            2. Use pdfplumber to read text page by page and record page-count metrics.
            3. Generate page_text artifacts for pages with text and record an issue for empty pages.

        Args:
            item: PDF or non-PDF data item in the current workflow.

        Returns:
            DataItem: Data item with page-text artifacts appended and action updated.
        """
        if item.modality != "pdf":
            return item

        path = Path(item.payload["path"])
        with pdfplumber.open(path) as pdf:
            item.metrics["page_count"] = len(pdf.pages)
            for page_index, page in enumerate(pdf.pages, start=1):
                text = (page.extract_text() or "").strip()
                if not text:
                    item.issues.append({"type": "empty_pdf_page", "page": page_index})
                    continue
                item.artifacts.append(
                    Artifact(
                        id=f"{item.id}_page_{page_index}_text",
                        type="page_text",
                        text=text,
                        data={"page": page_index},
                        source_trace=SourceTrace(
                            file=str(path),
                            page=page_index,
                            bbox=None,
                            operator=self.operator_name,
                        ),
                    )
                )

        item.action = "parsed" if item.artifacts else "failed"
        if item.action == "failed":
            item.issues.append({"type": "no_pdf_text", "message": "PDF text extraction produced no text"})
        return item


class PdfLayoutExtractOperator(BaseOperator):
    operator_name = "pdf_layout_extract"

    def process(self, item: DataItem) -> DataItem:
        """Extract layout text blocks and image blocks from PDF pages.

        Business logic:
            1. Pass non-PDF samples through unchanged.
            2. Group page chars into block-line-span hierarchy via pdfplumber.
            3. Record image blocks and text blocks that meet the minimum character count,
               and write layout metrics.

        Args:
            item: PDF or non-PDF data item in the current workflow.

        Returns:
            DataItem: Data item with layout_text_block or pdf_image_block artifacts appended.
        """
        if item.modality != "pdf":
            return item

        path = Path(item.payload["path"])
        min_chars = int(self.config.get("min_chars", 20))
        layout_blocks = 0
        image_blocks = 0
        with pdfplumber.open(path) as pdf:
            for page_index, page in enumerate(pdf.pages, start=1):
                # Build block-line-span hierarchy from chars
                blocks = _group_chars_into_blocks(page)

                # Collect image blocks from pdfplumber page.images
                for img_index, img in enumerate(page.images, start=1):
                    image_blocks += 1
                    image_bbox = [
                        round(float(img.get("x0", 0)), 2),
                        round(float(img.get("top", 0)), 2),
                        round(float(img.get("x1", 0)), 2),
                        round(float(img.get("bottom", 0)), 2),
                    ]
                    item.artifacts.append(
                        Artifact(
                            id=f"{item.id}_page_{page_index}_image_{image_blocks}",
                            type="pdf_image_block",
                            data={"page": page_index, "block_index": img_index},
                            source_trace=SourceTrace(
                                file=str(path),
                                page=page_index,
                                bbox=image_bbox,
                                operator=self.operator_name,
                            ),
                        )
                    )

                for block_index, block in enumerate(blocks, start=1):
                    block_bbox = block["bbox"]

                    lines_text: list[str] = []
                    max_size = 0.0
                    for line in block.get("lines", []):
                        spans = line.get("spans", [])
                        line_text = "".join(span.get("text", "") for span in spans).strip()
                        if line_text:
                            lines_text.append(line_text)
                        for span in spans:
                            max_size = max(max_size, float(span.get("size", 0)))

                    text = " ".join(lines_text).strip()
                    if len(text) < min_chars:
                        continue

                    layout_blocks += 1
                    item.artifacts.append(
                        Artifact(
                            id=f"{item.id}_page_{page_index}_layout_{layout_blocks}",
                            type="layout_text_block",
                            text=text,
                            data={
                                "page": page_index,
                                "block_index": block_index,
                                "font_size_max": round(max_size, 2),
                            },
                            source_trace=SourceTrace(
                                file=str(path),
                                page=page_index,
                                bbox=[round(float(v), 2) for v in block_bbox],
                                operator=self.operator_name,
                            ),
                        )
                    )

        item.metrics["layout_text_blocks"] = layout_blocks
        item.metrics["pdf_image_blocks"] = image_blocks
        if item.artifacts:
            item.action = "parsed"
        return item
