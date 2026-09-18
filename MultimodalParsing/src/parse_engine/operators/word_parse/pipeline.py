from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.common import MarkdownChunkOperator, MarkdownRebuildOperator, ParseQualityAssessOperator
from parse_engine.utilities.pipeline import run_stages, stage_config
from parse_engine.operators.word_parse.document import WordMediaExtractOperator, WordStructureExtractOperator


def parse_word_item(item: DataItem, config: dict) -> DataItem:
    """Run the end-to-end Word parsing pipeline for one sample."""
    return run_stages(
        item,
        [
            WordStructureExtractOperator(stage_config(config, "structure")),
            WordMediaExtractOperator(stage_config(config, "media")),
            MarkdownRebuildOperator(stage_config(config, "markdown")),
            MarkdownChunkOperator(stage_config(config, "chunking", {"target_len": 1500})),
            ParseQualityAssessOperator(stage_config(config, "quality")),
        ],
    )
