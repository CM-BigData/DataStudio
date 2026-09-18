from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.common import MarkdownChunkOperator, MarkdownRebuildOperator, ParseQualityAssessOperator
from parse_engine.operators.html_parse.document import HtmlBodyExtractOperator
from parse_engine.utilities.pipeline import run_stages, stage_config


def parse_html_item(item: DataItem, config: dict) -> DataItem:
    """Run the end-to-end HTML parsing pipeline for one sample."""
    chunking = stage_config(config, "chunking", {"target_len": 1200})
    return run_stages(
        item,
        [
            HtmlBodyExtractOperator(stage_config(config, "body")),
            MarkdownRebuildOperator(stage_config(config, "markdown")),
            MarkdownChunkOperator(chunking),
            ParseQualityAssessOperator(stage_config(config, "quality")),
        ],
    )
