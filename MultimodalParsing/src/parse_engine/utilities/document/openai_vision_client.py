from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
from PIL import Image

from parse_engine.utilities.document.ocrflux_client import OcrFluxError


def parse_document_to_markdown(
    file_path: str | Path,
    *,
    model: str,
    api_key: str,
    api_base: str | None = None,
    prompt: str | None = None,
    max_pages: int = 32,
) -> str:
    """Parse an image or PDF into Markdown through an OpenAI-compatible vision model.

    Business logic:
        1. Convert PDFs into page images with pypdfium2, or open the image directly.
        2. Send each page image to a vision-capable chat completion model with a Markdown reconstruction prompt.
        3. Join page-level Markdown outputs into one document-level Markdown string.

    Args:
        file_path (str | Path): Local input file path for a PDF or image.
        model (str): Vision-capable model name for the OpenAI-compatible API.
        api_key (str): API key used for the remote request.
        api_base (str | None): Optional custom OpenAI-compatible base URL.
        prompt (str | None): Optional override prompt for page-level Markdown reconstruction.
        max_pages (int): Maximum number of pages to process from a PDF.

    Returns:
        str: Document-level Markdown text reconstructed from the vision model output.

    Examples:
        >>> isinstance(parse_document_to_markdown.__name__, str)
        True
    """
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise OcrFluxError("openai is required for the OpenAI-compatible document parser") from exc

    path = Path(file_path)
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if api_base:
        client_kwargs["base_url"] = api_base
    client = OpenAI(**client_kwargs)

    page_images = _load_page_images(path, max_pages=max_pages)
    page_texts: list[str] = []
    for page_index, image in enumerate(page_images, start=1):
        content = _image_to_data_url(image)
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt or _default_prompt(page_index, len(page_images))},
                            {"type": "image_url", "image_url": {"url": content}},
                        ],
                    }
                ],
                temperature=0.0,
            )
        except Exception as exc:
            raise OcrFluxError(f"OpenAI-compatible document parsing failed: {exc}") from exc
        message = response.choices[0].message.content if response.choices else ""
        text = _normalize_content(message)
        if text:
            page_texts.append(text)
    return "\n\n".join(page_texts).strip()


def _load_page_images(path: Path, *, max_pages: int) -> list[Image.Image]:
    """Load one or more page images from an image file or PDF.

    业务逻辑：
        1. For images, open the local file directly and return a single page image.
        2. For PDFs, render pages with pypdfium2 up to `max_pages`.
        3. Raise an OcrFluxError when rendering fails or no page images are produced.

    Args:
        path (Path): Local input file path.
        max_pages (int): Maximum number of PDF pages to render.

    Returns:
        list[Image.Image]: Loaded page images for downstream vision parsing.
    """
    if path.suffix.lower() != ".pdf":
        return [Image.open(path)]

    pdf = pdfium.PdfDocument(str(path))
    total_pages = min(len(pdf), max_pages)
    images: list[Image.Image] = []
    for page_index in range(total_pages):
        page = pdf[page_index]
        bitmap = page.render(scale=2)  # scale=2 → ~144 DPI equivalent
        image = bitmap.to_pil()
        images.append(image)
    if not images:
        raise OcrFluxError(f"No PDF page images were generated for {path}")
    return images


def _image_to_data_url(image: Image.Image) -> str:
    """Encode one image into a PNG data URL for image_url chat input.

    业务逻辑：
        1. Serialize the input image to PNG bytes in memory.
        2. Base64-encode the bytes.
        3. Return a `data:image/png;base64,...` URL string.

    Args:
        image (Image.Image): Page image to encode.

    Returns:
        str: PNG data URL used by the vision chat request.

    Examples:
        >>> _image_to_data_url(Image.new('RGB', (1, 1))).startswith('data:image/png;base64,')
        True
    """
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _normalize_content(content: Any) -> str:
    """Normalize message content from chat completions into plain text.

    业务逻辑：
        1. Return string content directly when the SDK already flattened it.
        2. Join text blocks when the SDK returns structured content arrays.
        3. Return an empty string when no usable text is present.

    Args:
        content (Any): Raw message content from the chat completion response.

    Returns:
        str: Normalized text content for one page.

    Examples:
        >>> _normalize_content('x')
        'x'
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(str(block["text"]))
        return "\n".join(parts).strip()
    return ""


def _default_prompt(page_index: int, total_pages: int) -> str:
    """Build the default Markdown reconstruction prompt for one page image.

    业务逻辑：
        1. Tell the model to read the page naturally and return Markdown only.
        2. Preserve headings and tables in readable Markdown form.
        3. Mention page context to reduce accidental omissions on multi-page PDFs.

    Args:
        page_index (int): One-based page index.
        total_pages (int): Total page count included in the request loop.

    Returns:
        str: Prompt string for the vision model.

    Examples:
        >>> 'Markdown' in _default_prompt(1, 2)
        True
    """
    return (
        f"Read page {page_index} of {total_pages} and return only clean Markdown for the visible document content. "
        "Preserve headings, paragraphs, lists, and tables. Do not add explanations or code fences."
    )
