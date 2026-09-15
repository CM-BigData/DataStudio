import asyncio
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

from parse_engine.models import DataItem
from parse_engine.operators.common.document_parse import DocumentParseOperator
from parse_engine.utilities.document import ocrflux_client


def test_document_parse_operator_writes_markdown_artifact(monkeypatch, tmp_path: Path) -> None:
    """Verify that document parsing writes one markdown artifact for PDF samples.

    Business logic:
        1. Create a temporary PDF file path and patch the OpenAI vision parser call.
        2. Run DocumentParseOperator with explicit workflow-facing provider params.
        3. Assert that intermediate markdown, markdown artifact, and parsed action are written.

    Args:
        monkeypatch: Pytest monkeypatch fixture.
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "markdown" in "markdown"
        True
    """
    pdf_path = tmp_path / "demo.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with pdf_path.open("wb") as pdf_file:
        writer.write(pdf_file)

    def fake_parse_document_to_markdown(*args, **kwargs):
        return "# Demo\n\nPDF demo text"

    monkeypatch.setattr(
        "parse_engine.operators.common.document_parse.parse_with_openai_vision",
        fake_parse_document_to_markdown,
    )

    item = DataItem.from_path(pdf_path)
    result = DocumentParseOperator(
        {
            "provider": "openai_compatible",
            "model": "gpt-4.1",
            "api_key": "test-key",
            "api_base": "https://api.example.com/v1",
            "max_pages": 1,
        }
    ).process(item)

    assert result.action == "parsed"
    assert result.intermediate["markdown"] == "# Demo\n\nPDF demo text"
    assert result.artifacts[0].type == "markdown"
    assert result.artifacts[0].data["provider"] == "openai_compatible"


def test_ocrflux_element_merge_response_uses_safe_literal_parser(monkeypatch, tmp_path: Path) -> None:
    args = ocrflux_client._OcrFluxArgs(
        model="test",
        url="http://127.0.0.1",
        port=8000,
        skip_cross_page_merge=False,
        max_page_retries=1,
    )

    async def valid_response(*args, **kwargs):
        body = {"choices": [{"message": {"content": "[(0, 0)]"}}]}
        return 200, json.dumps(body).encode("utf-8")

    monkeypatch.setattr(ocrflux_client, "_apost", valid_response)
    result = asyncio.run(ocrflux_client._process_task(args, "element_merge_detect", (["left"], ["right"])))
    assert result == [(0, 0)]

    marker = tmp_path / "executed.txt"

    async def malicious_response(*args, **kwargs):
        expression = f"__import__('pathlib').Path({str(marker)!r}).write_text('executed')"
        body = {"choices": [{"message": {"content": expression}}]}
        return 200, json.dumps(body).encode("utf-8")

    monkeypatch.setattr(ocrflux_client, "_apost", malicious_response)
    with pytest.raises(ocrflux_client.OcrFluxError, match="OCRFlux"):
        asyncio.run(ocrflux_client._process_task(args, "element_merge_detect", (["left"], ["right"])))
    assert not marker.exists()


@pytest.mark.parametrize("content", ["[(1, 0)]", "[(True, 0)]", "{'bad': 'shape'}"])
def test_ocrflux_element_merge_response_rejects_invalid_shapes(monkeypatch, content: str) -> None:
    args = ocrflux_client._OcrFluxArgs(
        model="test",
        url="http://127.0.0.1",
        port=8000,
        skip_cross_page_merge=False,
        max_page_retries=1,
    )

    async def invalid_response(*args, **kwargs):
        body = {"choices": [{"message": {"content": content}}]}
        return 200, json.dumps(body).encode("utf-8")

    monkeypatch.setattr(ocrflux_client, "_apost", invalid_response)
    with pytest.raises(ocrflux_client.OcrFluxError, match="OCRFlux"):
        asyncio.run(ocrflux_client._process_task(args, "element_merge_detect", (["left"], ["right"])))
