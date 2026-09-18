from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.common import DocumentParseOperator, MarkdownChunkOperator, ParseQualityAssessOperator
from parse_engine.operators.image_parse.metadata import ImageQualityInspectOperator
from parse_engine.utilities.pipeline import run_stages, stage_config


def parse_image_item(item: DataItem, config: dict) -> DataItem:
    """Run the end-to-end image parsing pipeline for one sample."""
    quality = stage_config(config, "image_quality", {"min_width": 64, "min_height": 64})
    parser = stage_config(
        config,
        "document_parse",
        {"provider": "openai_compatible", "model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY", "api_base_env": "OPENAI_BASE_URL", "max_pages": 1},
    )
    return run_stages(
        item,
        [
            ImageQualityInspectOperator(quality),
            DocumentParseOperator(parser),
            MarkdownChunkOperator(stage_config(config, "chunking", {"target_len": 1500})),
            ParseQualityAssessOperator(stage_config(config, "quality")),
        ],
    )
