from __future__ import annotations

from parse_engine.models import DataItem
from parse_engine.operators.common import DocumentParseOperator, MarkdownChunkOperator, ParseQualityAssessOperator
from parse_engine.utilities.pipeline import run_stages, stage_config


def parse_pdf_item(item: DataItem, config: dict) -> DataItem:
    """Run the end-to-end PDF parsing pipeline for one sample."""
    parser = stage_config(
        config,
        "document_parse",
        {"provider": "openai_compatible", "model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY", "api_base_env": "OPENAI_BASE_URL", "max_pages": 32},
    )
    return run_stages(
        item,
        [
            DocumentParseOperator(parser),
            MarkdownChunkOperator(stage_config(config, "chunking", {"target_len": 1500})),
            ParseQualityAssessOperator(stage_config(config, "quality")),
        ],
    )
