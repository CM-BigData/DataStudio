from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable

from .input_adapter import InputAdapter


class DataReader:
    def __init__(self, resolver: Any) -> None:
        """Initialize the data reader.

        Business logic:
            1. Store the path resolver function.
            2. Resolve configured paths consistently when reading JSONL, CSV, or image folders.
            3. Let the executor control relative-path bases while the reader focuses on data normalization.

        Args:
            resolver (Any): Path resolver function.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> reader = DataReader(lambda value: value)
            >>> callable(reader.resolver)
            True
        """
        self.resolver = resolver  # Path resolver used to convert configured paths into actual read paths.

    def read(self, workflow: dict[str, Any], input_config: dict[str, Any]) -> list[dict[str, Any]]:
        """Read the sample collection according to input type.

        Business logic:
            1. Read the input type from the input config.
            2. Convert JSONL inputs into text-sample lists.
            3. Convert CSV inputs into text-sample lists.
            4. Convert `image_folder` inputs into image-sample lists.
            5. Raise an error directly for unsupported types.

        Args:
            workflow (dict[str, Any]): Workflow config section that preserves interface context.
            input_config (dict[str, Any]): Input config section.

        Returns:
            list[dict[str, Any]]: Normalized sample list.

        Examples:
            >>> callable(DataReader(lambda value: value).read)
            True
        """
        input_type = input_config.get("type")
        if input_type in {"jsonl", "csv"}:  # JSONL and CSV also use the flexible adapter so field mapping works in real workflows.
            return InputAdapter(workflow, input_config, self.resolver).read()
        if input_type not in {"image_folder"}:  # Hand all other input types to the flexible input adapter.
            return InputAdapter(workflow, input_config, self.resolver).read()
        if input_type == "image_folder":  # Image folders depend on annotations.json to build the sample list.
            return self._read_image_folder(input_config)
        raise ValueError(f"Unsupported input.type: {input_type}")

    def _read_text_jsonl(self, path: Path) -> list[dict[str, Any]]:
        """Read a JSONL text dataset.

        Business logic:
            1. Read the JSONL file line by line.
            2. Skip blank lines.
            3. Build a placeholder sample with empty text and the original line number when JSON parsing fails.
            4. Convert raw records into the unified text-sample structure.

        Args:
            path (Path): JSONL file path.

        Returns:
            list[dict[str, Any]]: Normalized text-sample list.

        Examples:
            >>> isinstance(DataReader(lambda value: value)._read_text_jsonl, object)
            True
        """
        items = []
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):  # Line numbers help locate problematic samples in the source file.
                if not line.strip():  # Blank lines do not form samples and should not create meaningless records.
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    raw = {"id": f"line_{line_no}", "text": "", "label": "", "_invalid_json": True}
                items.append(_text_item(raw, path, line_no, "jsonl"))
        return items

    def _read_text_csv(self, path: Path) -> list[dict[str, Any]]:
        """Read a CSV text dataset.

        Business logic:
            1. Use `utf-8-sig` to support CSV files with a BOM.
            2. Read row fields by header name through `DictReader`.
            3. Start line numbers from 2 so they match real data rows.
            4. Convert each row into the unified text-sample structure.

        Args:
            path (Path): CSV file path.

        Returns:
            list[dict[str, Any]]: Normalized text-sample list.

        Examples:
            >>> isinstance(DataReader(lambda value: value)._read_text_csv, object)
            True
        """
        items = []
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for line_no, raw in enumerate(reader, start=2):  # CSV row 1 is the header, so data rows start at line 2.
                items.append(_text_item(raw, path, line_no, "csv"))
        return items

    def _read_image_folder(self, input_config: dict[str, Any]) -> list[dict[str, Any]]:
        """Read an image folder and its annotation file.

        Business logic:
            1. Resolve the image root directory and annotation path.
            2. Read the annotation JSON array.
            3. Generate stable sequence IDs for images missing IDs.
            4. Resolve image paths to absolute paths and keep the remaining fields in `meta`.
            5. Build the unified image-sample structure.

        Args:
            input_config (dict[str, Any]): `image_folder` input config.

        Returns:
            list[dict[str, Any]]: Normalized image-sample list.

        Examples:
            >>> callable(DataReader(lambda value: value)._read_image_folder)
            True
        """
        root = self.resolver(input_config["path"])
        annotation_path = self.resolver(input_config.get("annotation_path", root / "annotations.json"))
        annotations = json.loads(annotation_path.read_text(encoding="utf-8"))
        items = []
        for index, raw in enumerate(annotations, start=1):  # Annotation order provides stable numbering for generated IDs.
            sample_id = str(raw.get("id") or f"image_{index:06d}")
            image_path = raw.get("image_path")
            resolved_image_path = str(self.resolver(root / image_path)) if image_path else None
            meta = {key: value for key, value in raw.items() if key not in {"id", "image_path"}}
            items.append(
                {
                    "id": sample_id,
                    "modality": "image",
                    "source": {"path": str(annotation_path), "format": "image_folder"},
                    "payload": {"image_path": resolved_image_path},
                    "meta": meta,
                    "intermediate": {},
                    "metrics": {},
                    "issues": [],
                    "action": "pending",
                }
            )
        return items


class DataWriter:
    @staticmethod
    def write_json(path: Path, payload: dict[str, Any]) -> None:
        """Write a JSON file.

        Business logic:
            1. Ensure the target directory exists.
            2. Serialize `payload` as indented JSON.
            3. Preserve non-ASCII characters to keep reports and summaries readable.

        Args:
            path (Path): Output JSON file path.
            payload (dict[str, Any]): Data to write.

        Returns:
            None: Writes directly to the file.

        Examples:
            >>> DataWriter.write_json(Path("tmp/write.json"), {})
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def append_jsonl(handle: Any, payload: dict[str, Any]) -> None:
        """Append a JSONL row to an open file.

        Business logic:
            1. Serialize `payload` into a single-line JSON string.
            2. Write a newline to form one JSONL record.
            3. Flush immediately to reduce result-loss risk during task interruption.

        Args:
            handle (Any): Open writable file handle.
            payload (dict[str, Any]): Data to append.

        Returns:
            None: Writes directly to the file handle.

        Examples:
            >>> callable(DataWriter.append_jsonl)
            True
        """
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        handle.flush()

    @staticmethod
    def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
        """Write a JSONL file.

        Business logic:
            1. Ensure the target directory exists.
            2. Open the JSONL file in write mode.
            3. Iterate through rows and reuse `append_jsonl` for writing.

        Args:
            path (Path): Output JSONL file path.
            rows (Iterable[dict[str, Any]]): Collection of records to write.

        Returns:
            None: Writes directly to the file.

        Examples:
            >>> DataWriter.write_jsonl(Path("tmp/write.jsonl"), [])
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:  # Write one row at a time so generator inputs do not need to be materialized eagerly.
                DataWriter.append_jsonl(handle, row)


def _text_item(raw: dict[str, Any], path: Path, line_no: int, data_format: str) -> dict[str, Any]:
    """Normalize a raw text record into the unified sample structure.

    Business logic:
        1. Read the raw ID and generate a temporary ID from the line number when missing.
        2. Copy raw fields into `payload`.
        3. Move non-`id` and non-`text` fields into `meta`.
        4. Mark whether the original ID was missing so schema operators can preserve that fact.
        5. Build the unified text-sample structure.

    Args:
        raw (dict[str, Any]): Raw text record.
        path (Path): Source file path.
        line_no (int): Source line number.
        data_format (str): Input format name.

    Returns:
        dict[str, Any]: Normalized text sample.

    Examples:
        >>> _text_item({"text": "hi"}, Path("a.jsonl"), 1, "jsonl")["id"]
        'text_line_1'
    """
    sample_id = str(raw.get("id") or f"text_line_{line_no}")
    payload = dict(raw)
    meta = {key: payload.pop(key) for key in list(payload.keys()) if key not in {"id", "text"}}
    meta["_missing_id"] = not bool(raw.get("id"))
    return {
        "id": sample_id,
        "modality": "text",
        "source": {"path": str(path), "format": data_format, "line_no": line_no},
        "payload": payload,
        "meta": meta,
        "intermediate": {},
        "metrics": {},
        "issues": [],
        "action": "pending",
    }
