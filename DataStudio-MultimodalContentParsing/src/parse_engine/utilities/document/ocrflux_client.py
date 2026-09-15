from __future__ import annotations

import ast
import asyncio
import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pypdfium2 as pdfium
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader


@dataclass(frozen=True)
class OcrFluxPageResponse:
    """Represent one OCRFlux page-to-Markdown response."""

    primary_language: str | None
    is_rotation_valid: bool
    rotation_correction: int
    is_table: bool
    is_diagram: bool
    natural_text: str | None


class OcrFluxError(RuntimeError):
    """Represent an OCRFlux client-side or server-side failure."""


def parse_document_to_markdown(
    file_path: str | Path,
    *,
    model: str,
    url: str,
    port: int,
    skip_cross_page_merge: bool = False,
    max_page_retries: int = 1,
) -> str:
    """Call an OCRFlux-compatible service and return document-level Markdown.

    Business logic:
        1. Build a lightweight OCRFlux request configuration for the target file.
        2. Run the async page-to-Markdown and optional merge flow.
        3. Return the final document_text field or raise an OCRFluxError on failure.

    Args:
        file_path (str | Path): Local input file path for a PDF or image.
        model (str): OCRFlux model name passed to the remote service.
        url (str): Base host URL without the OpenAI path suffix.
        port (int): OCRFlux service port.
        skip_cross_page_merge (bool): Whether to skip OCRFlux cross-page merge logic.
        max_page_retries (int): Maximum retries per OCRFlux page task.

    Returns:
        str: OCRFlux Markdown text for the full document.

    Examples:
        >>> isinstance(parse_document_to_markdown.__name__, str)
        True
    """
    args = _OcrFluxArgs(
        model=model,
        url=url,
        port=port,
        skip_cross_page_merge=skip_cross_page_merge,
        max_page_retries=max_page_retries,
    )
    result = asyncio.run(_request(args, str(file_path)))
    if not result or not result.get("document_text"):
        raise OcrFluxError("OCRFlux returned empty document_text")
    return str(result["document_text"])


@dataclass(frozen=True)
class _OcrFluxArgs:
    model: str
    url: str
    port: int
    skip_cross_page_merge: bool
    max_page_retries: int


def _build_page_to_markdown_prompt() -> str:
    return (
        "Below is the image of one page of a document. "
        "Just return the plain text representation of this document as if you were reading it naturally.\n"
        "ALL tables should be presented in HTML format.\n"
        "If there are images or figures in the page, present them as "
        '"<Image>(left,top),(right,bottom)</Image>", '
        "(left,top,right,bottom) are the coordinates of the top-left and bottom-right corners of the image or figure.\n"
        "Present all titles and headings as H1 headings.\n"
        "Do not hallucinate.\n"
    )


def _build_element_merge_detect_prompt(text_list_1: list[str], text_list_2: list[str]) -> str:
    task = (
        "Below are two consecutive pages in Markdown format, where each element of them is numbered. "
        "Identify pairs of elements which should be merged across the two pages, such as text paragraphs "
        "or tables that span across the two pages. Return pairs as "
        "[(element_index_of_page1, element_index_of_page2), ...] or [] if no elements should be merged.\n"
    )
    task += "Previous page:\n"
    for index, text in enumerate(text_list_1):
        task += f"{index}. {text}\n\n"
    task += "Next page:\n"
    for index, text in enumerate(text_list_2):
        task += f"{index}. {text}\n\n"
    return task


def _build_html_table_merge_prompt(table_1: str, table_2: str) -> str:
    return (
        "Below are two tables in HTML format, merge them into one table in HTML format.\n"
        f"TABLE 1:\n{table_1}\n"
        f"TABLE 2:\n{table_2}\n"
    )


def _get_page_image(
    file_path: str,
    page_number: int,
    target_longest_image_dim: int = 1024,
    image_rotation: int = 0,
) -> Image.Image:
    if file_path.lower().endswith(".pdf"):
        pdf = pdfium.PdfDocument(file_path)
        if page_number < 1 or page_number > len(pdf):
            raise OcrFluxError(f"Page {page_number} out of range for {file_path}")
        page = pdf[page_number - 1]
        bitmap = page.render(scale=1)  # scale=1 → 72 DPI
        image = bitmap.to_pil()
    else:
        image = Image.open(file_path)
    if image_rotation:
        image = image.rotate(-image_rotation, expand=True)
    width, height = image.size
    if width > height:
        new_width = target_longest_image_dim
        new_height = int(height * (target_longest_image_dim / width))
    else:
        new_height = target_longest_image_dim
        new_width = int(width * (target_longest_image_dim / height))
    return image.resize((new_width, new_height))


def _build_page_to_markdown_query(args: _OcrFluxArgs, file_path: str, page_number: int, image_rotation: int = 0) -> dict[str, Any]:
    image = _get_page_image(
        file_path,
        page_number,
        target_longest_image_dim=1024,
        image_rotation=image_rotation,
    )
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_page_to_markdown_prompt()},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            }
        ],
        "temperature": 0.0,
    }


def _build_element_merge_detect_query(args: _OcrFluxArgs, text_list_1: list[str], text_list_2: list[str]) -> dict[str, Any]:
    image = Image.new("RGB", (28, 28), color="black")
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_element_merge_detect_prompt(text_list_1, text_list_2)},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            }
        ],
        "temperature": 0.0,
    }


def _build_html_table_merge_query(args: _OcrFluxArgs, text_1: str, text_2: str) -> dict[str, Any]:
    image = Image.new("RGB", (28, 28), color="black")
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return {
        "model": args.model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_html_table_merge_prompt(text_1, text_2)},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_base64}"}},
                ],
            }
        ],
        "temperature": 0.0,
    }


async def _apost(url: str, json_data: dict[str, Any]) -> tuple[int, bytes]:
    parsed_url = urlparse(url)
    host = parsed_url.hostname
    if not host:
        raise OcrFluxError(f"Invalid OCRFlux URL: {url}")
    port = parsed_url.port or 80
    path = parsed_url.path or "/"
    writer = None
    try:
        reader, writer = await asyncio.open_connection(host, port)
        payload = json.dumps(json_data)
        request = (
            f"POST {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            "Content-Type: application/json\r\n"
            f"Content-Length: {len(payload)}\r\n"
            "Connection: close\r\n\r\n"
            f"{payload}"
        )
        writer.write(request.encode())
        await writer.drain()
        status_line = await reader.readline()
        if not status_line:
            raise OcrFluxError("No response from OCRFlux server")
        status_parts = status_line.decode().strip().split(" ", 2)
        if len(status_parts) < 2:
            raise OcrFluxError(f"Malformed OCRFlux status line: {status_line.decode().strip()}")
        status_code = int(status_parts[1])

        headers: dict[str, str] = {}
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            key, _, value = line.decode().partition(":")
            headers[key.strip().lower()] = value.strip()
        if "content-length" not in headers:
            raise OcrFluxError("OCRFlux response missing content-length")
        response_body = await reader.readexactly(int(headers["content-length"]))
        return status_code, response_body
    finally:
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def _process_task(args: _OcrFluxArgs, task_name: str, task_args: tuple[Any, ...]) -> Any:
    completion_url = f"{args.url}:{args.port}/v1/chat/completions"
    last_error: Exception | None = None
    for attempt in range(args.max_page_retries):
        if task_name == "page_to_markdown":
            query = _build_page_to_markdown_query(args, *task_args)
        elif task_name == "element_merge_detect":
            query = _build_element_merge_detect_query(args, *task_args)
        elif task_name == "html_table_merge":
            query = _build_html_table_merge_query(args, *task_args)
        else:
            raise OcrFluxError(f"Unsupported OCRFlux task: {task_name}")
        query["temperature"] = 0.1 * attempt
        try:
            status_code, response_body = await _apost(completion_url, query)
            if status_code != 200:
                raise OcrFluxError(f"OCRFlux HTTP status {status_code}")
            response_data = json.loads(response_body)
            content = response_data["choices"][0]["message"]["content"]
            if task_name == "page_to_markdown":
                model_response = json.loads(content)
                page_response = OcrFluxPageResponse(**model_response)
                natural_text = page_response.natural_text or ""
                markdown_element_list: list[str] = []
                for text in natural_text.split("\n\n"):
                    if text.startswith("<Image>") and text.endswith("</Image>"):
                        continue
                    if text.startswith("<table>") and text.endswith("</table>"):
                        try:
                            markdown_element_list.append(_table_matrix_to_html(text))
                        except Exception:
                            markdown_element_list.append(text.replace("<t>", "").replace("<l>", "").replace("<lt>", ""))
                    else:
                        markdown_element_list.append(text)
                return markdown_element_list
            if task_name == "element_merge_detect":
                parsed = ast.literal_eval(content)
                if not isinstance(parsed, list):
                    raise OcrFluxError("OCRFlux element-merge response must be a list")
                index_pairs: list[tuple[int, int]] = []
                page_1_elements, page_2_elements = task_args
                for pair in parsed:
                    if (
                        not isinstance(pair, (list, tuple))
                        or len(pair) != 2
                        or any(not isinstance(index, int) or isinstance(index, bool) for index in pair)
                    ):
                        raise OcrFluxError("OCRFlux element-merge response contains an invalid index pair")
                    index_1, index_2 = pair
                    if not (0 <= index_1 < len(page_1_elements) and 0 <= index_2 < len(page_2_elements)):
                        raise OcrFluxError("OCRFlux element-merge response contains an out-of-range index")
                    index_pairs.append((index_1, index_2))
                return index_pairs
            if not (content.startswith("<table>") and content.endswith("</table>")):
                raise OcrFluxError("OCRFlux table-merge response is not an HTML table")
            return content
        except Exception as exc:
            last_error = exc
    if last_error is None:
        raise OcrFluxError(f"OCRFlux task failed without a concrete exception: {task_name}")
    if isinstance(last_error, OcrFluxError):
        raise last_error
    raise OcrFluxError(f"OCRFlux task failed after {args.max_page_retries} attempts: {last_error}") from last_error


def _is_html_table(text: str) -> bool:
    return BeautifulSoup(text, "html.parser").find("table") is not None


def _table_matrix_to_html(matrix_table: str) -> str:
    soup = BeautifulSoup(matrix_table, "html.parser")
    table = soup.find("table")
    if table is None:
        raise OcrFluxError("OCRFlux matrix table payload is missing a <table> node")
    rownum = 0
    colnum = 0
    cell_dict: dict[tuple[int, int], str] = {}
    rid = 0
    for tr in table.find_all("tr"):
        cid = 0
        for td in tr.find_all("td"):
            if td.find("l"):
                cell_dict[(rid, cid)] = "<l>"
            elif td.find("t"):
                cell_dict[(rid, cid)] = "<t>"
            elif td.find("lt"):
                cell_dict[(rid, cid)] = "<lt>"
            else:
                cell_dict[(rid, cid)] = td.get_text(strip=True)
            cid += 1
        if colnum == 0:
            colnum = cid
        elif cid != colnum:
            raise OcrFluxError("OCRFlux matrix table column count mismatch")
        rid += 1
    rownum = rid
    html_table = ["<table>"]
    for rid in range(rownum):
        html_table.append("<tr>")
        for cid in range(colnum):
            if (rid, cid) not in cell_dict:
                continue
            text = cell_dict[(rid, cid)]
            if text in {"<l>", "<t>", "<lt>"}:
                raise OcrFluxError("OCRFlux matrix table merge markers are inconsistent")
            rowspan = 1
            colspan = 1
            for row_index in range(rid + 1, rownum):
                if cell_dict.get((row_index, cid)) == "<t>":
                    rowspan += 1
                    del cell_dict[(row_index, cid)]
                else:
                    break
            for col_index in range(cid + 1, colnum):
                if cell_dict.get((rid, col_index)) == "<l>":
                    colspan += 1
                    del cell_dict[(rid, col_index)]
                else:
                    break
            for row_index in range(rid + 1, rid + rowspan):
                for col_index in range(cid + 1, cid + colspan):
                    if cell_dict.get((row_index, col_index)) != "<lt>":
                        raise OcrFluxError("OCRFlux matrix table rectangle markers are inconsistent")
                    del cell_dict[(row_index, col_index)]
            attrs = ""
            if rowspan > 1:
                attrs += f' rowspan="{rowspan}"'
            if colspan > 1:
                attrs += f' colspan="{colspan}"'
            html_table.append(f"<td{attrs}>{text}</td>")
        html_table.append("</tr>")
    html_table.append("</table>")
    return "".join(html_table)


def _build_document_text(
    page_to_markdown_result: dict[int, list[str]],
    element_merge_detect_result: dict[tuple[int, int], list[tuple[int, int]]],
    html_table_merge_result: dict[tuple[int, int, int, int], str],
) -> str:
    for page_1, page_2, elem_idx_1, elem_idx_2 in sorted(html_table_merge_result.keys(), key=lambda key: -key[0]):
        page_to_markdown_result[page_1][elem_idx_1] = html_table_merge_result[(page_1, page_2, elem_idx_1, elem_idx_2)]
        page_to_markdown_result[page_2][elem_idx_2] = ""
    for page_1, page_2 in sorted(element_merge_detect_result.keys(), key=lambda key: -key[0]):
        for elem_idx_1, elem_idx_2 in element_merge_detect_result[(page_1, page_2)]:
            if (
                len(page_to_markdown_result[page_1][elem_idx_1]) == 0
                or page_to_markdown_result[page_1][elem_idx_1][-1] == "-"
                or ("\u4e00" <= page_to_markdown_result[page_1][elem_idx_1][-1] <= "\u9fff")
            ):
                page_to_markdown_result[page_1][elem_idx_1] += page_to_markdown_result[page_2][elem_idx_2]
            else:
                page_to_markdown_result[page_1][elem_idx_1] += " " + page_to_markdown_result[page_2][elem_idx_2]
            page_to_markdown_result[page_2][elem_idx_2] = ""
    document_text_list: list[str] = []
    for page in list(page_to_markdown_result.keys()):
        document_text_list.extend([text for text in page_to_markdown_result[page] if text])
    return "\n\n".join(document_text_list)


async def _request(args: _OcrFluxArgs, file_path: str) -> dict[str, Any] | None:
    if file_path.lower().endswith(".pdf"):
        try:
            num_pages = PdfReader(file_path).get_num_pages()
        except Exception:
            return None
    else:
        num_pages = 1
    try:
        page_tasks: list[asyncio.Task[Any]] = []
        async with asyncio.TaskGroup() as task_group:
            for page_number in range(1, num_pages + 1):
                page_tasks.append(task_group.create_task(_process_task(args, "page_to_markdown", (file_path, page_number))))
        page_results = [task.result() for task in page_tasks]
        page_to_markdown_result: dict[int, list[str]] = {}
        for index, result in enumerate(page_results, start=1):
            if result is not None:
                page_to_markdown_result[index] = result
        page_texts: dict[str, str] = {}
        fallback_pages: list[int] = []
        for page_number in range(1, num_pages + 1):
            if page_number not in page_to_markdown_result:
                fallback_pages.append(page_number - 1)
            else:
                page_texts[str(page_number - 1)] = "\n\n".join(page_to_markdown_result[page_number])
        if args.skip_cross_page_merge:
            return {
                "page_texts": page_texts,
                "fallback_pages": fallback_pages,
                "document_text": _build_document_text(page_to_markdown_result, {}, {}),
            }
        element_merge_tasks: list[asyncio.Task[Any]] = []
        async with asyncio.TaskGroup() as task_group:
            for page_number in range(1, num_pages):
                if page_number in page_to_markdown_result and page_number + 1 in page_to_markdown_result:
                    element_merge_tasks.append(
                        task_group.create_task(
                            _process_task(
                                args,
                                "element_merge_detect",
                                (page_to_markdown_result[page_number], page_to_markdown_result[page_number + 1]),
                            )
                        )
                    )
        element_merge_detect_result: dict[tuple[int, int], list[tuple[int, int]]] = {}
        for page_number, task in enumerate(element_merge_tasks, start=1):
            result = task.result()
            if result:
                element_merge_detect_result[(page_number, page_number + 1)] = result
        table_merge_tasks: list[tuple[tuple[int, int, int, int], asyncio.Task[Any]]] = []
        async with asyncio.TaskGroup() as task_group:
            for (page_1, page_2), index_pairs in element_merge_detect_result.items():
                for elem_idx_1, elem_idx_2 in index_pairs:
                    text_1 = page_to_markdown_result[page_1][elem_idx_1]
                    text_2 = page_to_markdown_result[page_2][elem_idx_2]
                    if _is_html_table(text_1) and _is_html_table(text_2):
                        task = task_group.create_task(_process_task(args, "html_table_merge", (text_1, text_2)))
                        table_merge_tasks.append(((page_1, page_2, elem_idx_1, elem_idx_2), task))
        html_table_merge_result = {
            key: task.result()
            for key, task in table_merge_tasks
            if task.result() is not None
        }
        return {
            "page_texts": page_texts,
            "fallback_pages": fallback_pages,
            "document_text": _build_document_text(page_to_markdown_result, element_merge_detect_result, html_table_merge_result),
        }
    except Exception as exc:
        raise OcrFluxError(f"OCRFlux request failed: {exc}") from exc
