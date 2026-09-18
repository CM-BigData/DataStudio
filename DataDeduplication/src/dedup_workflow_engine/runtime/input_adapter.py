from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Iterable

from dedup_workflow_engine.runtime.loader import resolve_path


SUPPORTED_INPUT_TYPES = {"auto", "jsonl", "json", "csv", "directory", "file", "stdin", "raw_text"}  # Input config: supported workflow input types.
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}  # Input config: extensions that can be read into payload.text.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".ppm", ".pgm", ".tif", ".tiff"}  # Input config: extensions that can be read into payload.image_path.
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wma"}  # Input config: extensions that can be read into payload.audio_path.
JSON_EXTENSIONS = {".json"}  # Input config: extensions that can be read as JSON.
JSONL_EXTENSIONS = {".jsonl", ".ndjson"}  # Input config: extensions that can be read as JSONL.
CSV_EXTENSIONS = {".csv"}  # Input config: extensions that can be read as CSV.


def _pure_stem(path_value: object) -> str:
    """Extract a filename stem without resolving the path on the filesystem."""
    text = str(path_value)
    return PureWindowsPath(text).stem if "\\" in text else PurePath(text).stem


class DedupItemNormalizer:
    def __init__(self, input_config: dict[str, Any] | None = None) -> None:
        """Create a deduplication sample normalizer.

        Business logic:
            1. Store field mappings from workflow input config.
            2. Convert strings, dictionaries, or other raw values into dict samples.
            3. Preserve non-core fields in payload for custom operators.

        Args:
            input_config (dict[str, Any] | None): Workflow input config.

        Returns:
            None: This initializer does not return a value.

        Examples:
            >>> DedupItemNormalizer({"text_field": "body"}).input_config["text_field"]
            'body'
        """
        self.input_config = input_config or {}  # Input config: field mappings and default modality source.

    def normalize(self, raw_item: Any, source: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convert flexible input into a deduplication sample dict.

        Business logic:
            1. Accept a dict, string, or other raw value.
            2. Identify id, modality, text, image_path, audio_path, and payload.
            3. Fill in meta, intermediate, metrics, issues, and action fields.

        Args:
            raw_item (Any): One record split from user input.
            source (dict[str, Any] | None): Input-source metadata.

        Returns:
            dict[str, Any]: Standard sample ready to enter the dedup workflow.

        Examples:
            >>> DedupItemNormalizer().normalize("hello")["payload"]["text"]
            'hello'
        """
        raw = dict(raw_item) if isinstance(raw_item, dict) else {"text": "" if raw_item is None else str(raw_item)}
        payload = self._resolve_payload(raw)
        item_id = self._read_mapped_value(raw, "id_field", ["id", "sample_id", "uid"])
        modality = self._read_mapped_value(raw, "modality_field", ["modality", "type"])
        text_value = self._read_mapped_value(raw, "text_field", ["text", "content", "body"])
        image_value = self._read_mapped_value(raw, "image_path_field", ["image_path", "image", "path"])
        audio_value = self._read_mapped_value(raw, "audio_path_field", ["audio_path", "audio", "path"])
        if text_value is not None:  # Normalize text content into payload.text.
            payload.setdefault("text", str(text_value))
        if image_value not in (None, "") and "text" not in payload:  # Image paths should enter the image workflow unless explicit text is present.
            payload.setdefault("image_path", str(image_value))
        if audio_value not in (None, "") and "text" not in payload and "image_path" not in payload:  # Audio paths rank below explicit text and image payloads.
            payload.setdefault("audio_path", str(audio_value))

        output = {
            "id": str(item_id) if item_id not in (None, "") else self._make_id(source, payload),
            "modality": self._infer_modality(str(modality or self.input_config.get("modality", "unknown")), payload),
            "payload": payload,
            "meta": dict(raw.get("meta", {})) if isinstance(raw.get("meta"), dict) else {},
            "intermediate": dict(raw.get("intermediate", {})) if isinstance(raw.get("intermediate"), dict) else {},
            "metrics": dict(raw.get("metrics", {})) if isinstance(raw.get("metrics"), dict) else {},
            "issues": list(raw.get("issues", [])) if isinstance(raw.get("issues"), list) else [],
            "action": str(raw.get("action", "pending")),
        }
        output["meta"].setdefault("input_source", source or {})
        return output

    def _resolve_payload(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Resolve payload from user input.

        Business logic:
            1. Prefer an explicit payload object when present.
            2. Preserve extra non-core fields as payload supplements.
            3. Avoid overwriting fields the user already placed inside payload.

        Args:
            raw (dict[str, Any]): Raw input record.

        Returns:
            dict[str, Any]: Normalized payload.

        Examples:
            >>> DedupItemNormalizer()._resolve_payload({"payload": {"a": 1}, "b": 2})["b"]
            2
        """
        payload = dict(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {}
        reserved = {"id", "sample_id", "uid", "modality", "type", "text", "content", "body", "path", "image", "image_path", "audio", "audio_path", "payload", "meta", "intermediate", "metrics", "issues", "action"}
        for key, value in raw.items():  # Preserve extra fields for custom operators.
            if key not in reserved and key not in payload:  # Do not overwrite explicit payload keys.
                payload[key] = value
        return payload

    def _read_mapped_value(self, raw: dict[str, Any], config_key: str, candidates: list[str]) -> Any:
        """Read an explicit mapping or fallback candidate field.

        Business logic:
            1. Read the explicit field name from input config first.
            2. Then look through common fallback field names.
            3. Return None when nothing matches.

        Args:
            raw (dict[str, Any]): Raw record.
            config_key (str): Field-mapping config key.
            candidates (list[str]): Candidate field-name list.

        Returns:
            Any: Matched field value, or None.

        Examples:
            >>> DedupItemNormalizer({"id_field": "sid"})._read_mapped_value({"sid": "1"}, "id_field", [])
            '1'
        """
        keys = [self.input_config.get(config_key), *candidates]
        for key in keys:  # Explicit mappings take priority over default candidates.
            if key and key in raw:  # Return immediately after the first available match.
                return raw[key]
        return None

    def _infer_modality(self, configured: str, payload: dict[str, Any]) -> str:
        """Infer the sample modality.

        Business logic:
            1. Prefer a valid explicit modality.
            2. Infer from payload.text, image_path, or audio_path.
            3. Return unknown when inference is impossible.

        Args:
            configured (str): Modality from user config or the record itself.
            payload (dict[str, Any]): Normalized payload.

        Returns:
            str: text, image, audio, or unknown.

        Examples:
            >>> DedupItemNormalizer()._infer_modality("unknown", {"text": "x"})
            'text'
        """
        if configured in {"text", "image", "audio"}:  # A valid explicit modality takes priority.
            return configured
        if "text" in payload:  # Text fields go into text deduplication.
            return "text"
        if "image_path" in payload:  # Image paths go into image deduplication.
            return "image"
        if "audio_path" in payload:  # Audio paths go into audio deduplication.
            return "audio"
        return "unknown"

    def _make_id(self, source: dict[str, Any] | None, payload: dict[str, Any]) -> str:
        """Generate a default sample id.

        Business logic:
            1. Prefer filenames for path-based payloads.
            2. Use line numbers for line-based input.
            3. Fall back to the current nanosecond timestamp when source data is insufficient.

        Args:
            source (dict[str, Any] | None): Input-source metadata.
            payload (dict[str, Any]): Normalized payload.

        Returns:
            str: Sample id.

        Examples:
            >>> DedupItemNormalizer()._make_id({"line": 2}, {}).startswith("sample_2")
            True
        """
        for key in ("image_path", "audio_path"):  # Media paths can provide stable file names.
            if payload.get(key):  # Use the first available media path.
                return _pure_stem(payload[key])
        source = source or {}
        if source.get("path"):  # Use the filename for text-file input.
            return _pure_stem(source["path"])
        if source.get("line") is not None:  # Use line numbers to generate stable sample names.
            return f"sample_{source['line']}"
        return f"sample_{time.time_ns()}"


class InputAdapter:
    def __init__(self, input_config: dict[str, Any], base_dir: Path | None = None) -> None:
        """Create a deduplication input adapter.

        Business logic:
            1. Store workflow input config.
            2. Store the base directory for resolving relative paths.
            3. Initialize the sample normalizer.

        Args:
            input_config (dict[str, Any]): Workflow input config.
            base_dir (Path | None): Base directory used to resolve relative paths.

        Returns:
            None: This initializer does not return a value.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).input_config["type"]
            'raw_text'
        """
        self.input_config = input_config  # Input config: workflow input section.
        self.base_dir = base_dir or Path.cwd()  # Input config: base directory for resolving relative paths.
        self.normalizer = DedupItemNormalizer(input_config)  # Input config: reuse dict-sample normalization rules.

    def read(self) -> Iterable[dict[str, Any]]:
        """Read input and yield deduplication samples.

        Business logic:
            1. Resolve the actual input type.
            2. Dispatch to the concrete reader by type.
            3. Yield standardized dict samples one by one.

        Args:
            None: No input parameters.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> list(InputAdapter({"type": "raw_text", "text": "x"}).read())[0]["payload"]["text"]
            'x'
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # Configured text becomes a single sample directly.
            yield self.normalizer.normalize({"text": str(self.input_config.get("text", ""))}, {"type": "raw_text"})
            return
        if input_type == "stdin":  # Standard input does not need a path.
            yield from self._read_stdin()
            return
        path = self._required_path()
        if input_type == "jsonl":  # Read JSONL line by line.
            yield from self._read_jsonl(path)
        elif input_type == "json":  # Read JSON objects or arrays.
            yield from self._read_json(path)
        elif input_type == "csv":  # Read CSV line by line.
            yield from self._read_csv(path)
        elif input_type == "directory":  # Read directories by file extension.
            yield from self._read_directory(path)
        elif input_type == "file":  # Read a single file by its extension.
            yield from self._read_file(path)
        else:
            raise ValueError(f"unsupported input.type: {input_type}")

    def validate_config(self) -> None:
        """Validate input config.

        Business logic:
            1. Check whether input.type is supported.
            2. Check required fields for raw_text, stdin, and path-based input.
            3. Check path existence and directory/file type.

        Args:
            None: No input parameters.

        Returns:
            None: Raises an exception when validation fails.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).validate_config()
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # raw_text must provide text.
            if "text" not in self.input_config:  # Samples cannot be built when text is missing.
                raise ValueError("input.text is required when input.type=raw_text")
            return
        if input_type == "stdin":  # stdin is read lazily at runtime.
            return
        path = self._required_path()
        if not path.exists():  # Path-based input must exist.
            raise FileNotFoundError(f"Input path does not exist: {path}")
        if input_type == "directory" and not path.is_dir():  # Directory input types must point to a directory.
            raise ValueError(f"input.path must be a directory when input.type=directory: {path}")
        if input_type != "directory" and path.is_dir():  # Non-directory input types cannot point to a directory.
            raise ValueError(f"input.path must be a file when input.type={input_type}: {path}")

    def _resolve_input_type(self) -> str:
        """Resolve the actual input type.

        Business logic:
            1. Read input.type and default to auto when missing.
            2. Return explicit types directly.
            3. Infer auto types from path or text.

        Args:
            None: No input parameters.

        Returns:
            str: Actual input type.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"})._resolve_input_type()
            'raw_text'
        """
        configured = str(self.input_config.get("type", "auto"))
        if configured not in SUPPORTED_INPUT_TYPES:  # Accept only supported types.
            raise ValueError(f"unsupported input.type: {configured}")
        if configured != "auto":  # Explicit declarations take priority.
            return configured
        if "text" in self.input_config and "path" not in self.input_config:  # Treat input as raw_text when only text is provided.
            return "raw_text"
        path = self._required_path()
        if path.is_dir():  # Automatically detect directory paths as directory input.
            return "directory"
        suffix = path.suffix.lower()
        if suffix in JSONL_EXTENSIONS:  # Detect JSONL by its extension.
            return "jsonl"
        if suffix in JSON_EXTENSIONS:  # Detect JSON by its extension.
            return "json"
        if suffix in CSV_EXTENSIONS:  # Detect CSV by its extension.
            return "csv"
        return "file"

    def _required_path(self) -> Path:
        """Read and resolve input.path.

        Business logic:
            1. Check whether input.path is declared.
            2. Use absolute paths directly.
            3. Resolve relative paths against the configured base directory.

        Args:
            None: No input parameters.

        Returns:
            Path: Resolved path.

        Examples:
            >>> isinstance(InputAdapter({"type": "file", "path": "a.txt"})._required_path(), Path)
            True
        """
        if not self.input_config.get("path"):  # Path-based input must declare path.
            raise ValueError("input.path is required for path-based input types")
        return resolve_path(str(self.input_config["path"]), self.base_dir)

    def _read_jsonl(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSONL input.

        Business logic:
            1. Read line by line and skip blank lines.
            2. Parse each line into a JSON object.
            3. Normalize each record into a deduplication sample.

        Args:
            path (Path): JSONL path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_jsonl)
            True
        """
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_no, line in enumerate(handle, start=1):  # Line numbers are preserved for input-source auditability.
                if not line.strip():  # Blank lines do not generate samples.
                    continue
                yield self.normalizer.normalize(json.loads(line), {"type": "jsonl", "path": str(path), "line": line_no})

    def _read_json(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSON object or array input.

        Business logic:
            1. Parse the JSON file.
            2. Treat arrays as multiple records.
            3. Treat objects as single records.

        Args:
            path (Path): JSON path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_json)
            True
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Array order determines sample order.
            yield self.normalizer.normalize(raw, {"type": "json", "path": str(path), "line": index})

    def _read_csv(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read CSV input.

        Business logic:
            1. Read rows with DictReader using the header.
            2. Treat each row's fields as the sample source.
            3. Normalize rows into deduplication samples.

        Args:
            path (Path): CSV path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_csv)
            True
        """
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):  # Each line after the header corresponds to one sample.
                yield self.normalizer.normalize(dict(row), {"type": "csv", "path": str(path), "line": line_no})

    def _read_directory(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read directory input.

        Business logic:
            1. Traverse non-hidden files in the directory in sorted order.
            2. Generate text, image, or audio samples according to file extension.
            3. Delegate structured files to the matching reader.

        Args:
            path (Path): Input directory path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_directory)
            True
        """
        for file_path in sorted(item for item in path.rglob("*") if item.is_file() and not item.name.startswith(".")):  # Sorting keeps output stable.
            if file_path.suffix.lower() in TEXT_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | JSON_EXTENSIONS | JSONL_EXTENSIONS | CSV_EXTENSIONS:  # Read only supported formats.
                yield from self._read_file(file_path)

    def _read_file(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read single-file input.

        Business logic:
            1. Delegate JSON, JSONL, and CSV files to the corresponding readers.
            2. Read text-file content into payload.text.
            3. Read image and audio files as paths into the corresponding payload field.

        Args:
            path (Path): Input file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_file)
            True
        """
        suffix = path.suffix.lower()
        if suffix in JSON_EXTENSIONS:  # Delegate JSON files to the JSON reader.
            yield from self._read_json(path)
        elif suffix in JSONL_EXTENSIONS:  # Delegate JSONL files to the JSONL reader.
            yield from self._read_jsonl(path)
        elif suffix in CSV_EXTENSIONS:  # Delegate CSV files to the CSV reader.
            yield from self._read_csv(path)
        elif suffix in TEXT_EXTENSIONS:  # Read the full text content of text files.
            yield self.normalizer.normalize({"id": path.stem, "text": path.read_text(encoding="utf-8")}, {"type": "file", "path": str(path)})
        elif suffix in IMAGE_EXTENSIONS:  # Use image files by path.
            yield self.normalizer.normalize({"id": path.stem, "modality": "image", "payload": {"image_path": str(path)}}, {"type": "file", "path": str(path)})
        elif suffix in AUDIO_EXTENSIONS:  # Use audio files by path.
            yield self.normalizer.normalize({"id": path.stem, "modality": "audio", "payload": {"audio_path": str(path)}}, {"type": "file", "path": str(path)})
        else:
            yield self.normalizer.normalize({"id": path.stem, "payload": {"path": str(path)}}, {"type": "file", "path": str(path)})

    def _read_stdin(self) -> Iterable[dict[str, Any]]:
        """Read standard input.

        Business logic:
            1. Read all content from sys.stdin.
            2. Try parsing it as a JSON object or array.
            3. Treat it as a text sample when parsing fails.

        Args:
            None: No input parameters.

        Returns:
            Iterable[dict[str, Any]]: Iterator of standardized deduplication samples.

        Examples:
            >>> callable(InputAdapter({"type": "stdin"})._read_stdin)
            True
        """
        text = sys.stdin.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            yield self.normalizer.normalize({"text": text}, {"type": "stdin"})
            return
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # JSON arrays generate samples in order.
            yield self.normalizer.normalize(raw, {"type": "stdin", "line": index})
