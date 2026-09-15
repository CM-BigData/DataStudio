from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.common import MarkdownChunkOperator, MarkdownRebuildOperator, ParseQualityAssessOperator
from parse_engine.operators.excel_parse.document import ExcelStructureExtractOperator
from parse_engine.utilities.pipeline import run_stages, stage_config


def parse_excel_item(item: DataItem, config: dict) -> DataItem:
    """Run the end-to-end Excel parsing pipeline for one sample."""
    chunking = stage_config(config, "chunking", {"target_len": 800})
    return run_stages(
        item,
        [
            ExcelStructureExtractOperator(stage_config(config, "structure")),
            MarkdownRebuildOperator(stage_config(config, "markdown")),
            MarkdownChunkOperator(chunking),
            ParseQualityAssessOperator(stage_config(config, "quality")),
        ],
    )
