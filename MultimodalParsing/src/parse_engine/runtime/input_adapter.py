from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Iterable

from parse_engine.models import DataItem, Modality

SUPPORTED_INPUT_TYPES = {"auto", "file_dir", "directory", "file", "jsonl", "json", "csv", "stdin", "raw_text"}  # Input config: set of input types supported by the workflow.
SUPPORTED_MEDIA_SUFFIXES = {".pdf", ".docx", ".xls", ".xlsx", ".html", ".htm", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".wav", ".mp3", ".m4a", ".flac", ".aac"}  # Input config: media extensions that can enter the parsing pipeline as file-path samples.
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}  # Input config: extensions that can be read as text content.
JSON_EXTENSIONS = {".json"}  # Input config: extensions that can be read as JSON.
JSONL_EXTENSIONS = {".jsonl", ".ndjson"}  # Input config: extensions that can be read as JSONL.
CSV_EXTENSIONS = {".csv"}  # Input config: extensions that can be read as CSV.


def _pure_path(path_value: object) -> PurePath:
    """Create a non-resolving pure path for POSIX or Windows-style strings."""
    text = str(path_value)
    return PureWindowsPath(text) if "\\" in text else PurePath(text)


class DataItemNormalizer:
    def __init__(self, input_config: dict[str, Any] | None = None) -> None:
        """Create a parsing sample normalizer.

        Business logic:
            1. Store field-mapping configuration from workflow input.
            2. Convert strings, dictionaries, or other raw values into DataItem objects.
            3. Preserve input-source metadata so run artifacts can be traced.

        Args:
            input_config (dict[str, Any] | None): Workflow input configuration.

        Returns:
            None: The initializer does not return business data.

        Examples:
            >>> DataItemNormalizer({"text_field": "content"}).input_config["text_field"]
            'content'
        """
        self.input_config = input_config or {}  # Input config: source of field mappings and type inference.

    def normalize(self, raw_item: Any, source: dict[str, Any] | None = None) -> DataItem:
        """Convert loose input into a DataItem.

        Business logic:
            1. Accept dictionaries, strings, or other raw values.
            2. Recognize common fields such as id, modality, path, text, and payload.
            3. Build a DataItem and write input_source tracing information.

        Args:
            raw_item (Any): One record after the user's input has been split.
            source (dict[str, Any] | None): Metadata describing the input source.

        Returns:
            DataItem: Standard sample ready to enter the parsing workflow.

        Examples:
            >>> DataItemNormalizer().normalize("hello").payload["text"]
            'hello'
        """
        raw = dict(raw_item) if isinstance(raw_item, dict) else {"text": "" if raw_item is None else str(raw_item)}
        payload = self._resolve_payload(raw)
        item_id = self._read_mapped_value(raw, "id_field", ["id", "sample_id", "uid"])
        modality = str(self._read_mapped_value(raw, "modality_field", ["modality", "type"]) or "unknown")
        path_value = self._read_mapped_value(raw, "path_field", ["path", "file", "filepath", "source_path"])
        text_value = self._read_mapped_value(raw, "text_field", ["text", "content", "markdown", "transcript"])
        source_info = dict(raw.get("source", {})) if isinstance(raw.get("source"), dict) else {}
        if path_value not in (None, ""):  # Preserve the original path declared by the user.
            source_info.setdefault("path", str(path_value))
            source_info.setdefault("format", _pure_path(path_value).suffix.lstrip("."))
            payload.setdefault("path", str(path_value))
        if text_value is not None:  # Normalize body text from loose input into payload.text.
            payload.setdefault("text", str(text_value))

        source_info["input_source"] = source or {}
        return DataItem(
            id=str(item_id) if item_id not in (None, "") else self._make_id(source, path_value),
            modality=self._validate_modality(modality),
            source=source_info,
            payload=payload,
            meta=dict(raw.get("meta", {})) if isinstance(raw.get("meta"), dict) else {},
            intermediate=dict(raw.get("intermediate", {})) if isinstance(raw.get("intermediate"), dict) else {},
            metrics=dict(raw.get("metrics", {})) if isinstance(raw.get("metrics"), dict) else {},
            issues=list(raw.get("issues", [])) if isinstance(raw.get("issues"), list) else [],
            artifacts=list(raw.get("artifacts", [])) if isinstance(raw.get("artifacts"), list) else [],
            action=str(raw.get("action", "pending")),
        )

    def _resolve_payload(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Resolve the payload from user input.

        Business logic:
            1. Prefer an explicit payload object when present.
            2. Preserve additional non-core fields as payload supplements.
            3. Avoid overwriting fields the user has already put into payload.

        Args:
            raw (dict[str, Any]): Raw input record.

        Returns:
            dict[str, Any]: Normalized payload.

        Examples:
            >>> DataItemNormalizer()._resolve_payload({"payload": {"a": 1}, "b": 2})["a"]
            1
        """
        payload = dict(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {}
        reserved = {"id", "sample_id", "uid", "modality", "type", "path", "file", "filepath", "source_path", "text", "content", "markdown", "transcript", "source", "payload", "meta", "intermediate", "metrics", "issues", "artifacts", "action"}
        for key, value in raw.items():  # Preserve extra fields so custom operators can use them.
            if key not in reserved and key not in payload:  # Only add non-core fields that were not explicitly written into payload.
                payload[key] = value
        return payload

    def _read_mapped_value(self, raw: dict[str, Any], config_key: str, candidates: list[str]) -> Any:
        """Read an explicit mapping or candidate field.

        Business logic:
            1. Read the explicit field name from input configuration first.
            2. Then try common candidate field names.
            3. Return None if nothing matches.

        Args:
            raw (dict[str, Any]): Raw record.
            config_key (str): Field-mapping configuration name.
            candidates (list[str]): List of candidate field names.

        Returns:
            Any: Matched field value, or None.

        Examples:
            >>> DataItemNormalizer({"id_field": "sid"})._read_mapped_value({"sid": "1"}, "id_field", [])
            '1'
        """
        keys = [self.input_config.get(config_key), *candidates]
        for key in keys:  # Explicit fields take precedence over default candidates.
            if key and key in raw:  # Return immediately after the first usable match.
                return raw[key]
        return None

    def _validate_modality(self, value: str) -> Modality:
        """Validate a parsing modality.

        Business logic:
            1. Accept the modality from user input.
            2. Allow only the built-in DataItem modality set.
            3. Treat invalid values as unknown to avoid failing too early on loose input.

        Args:
            value (str): Modality value from user input.

        Returns:
            Modality: Valid parsing modality.

        Examples:
            >>> DataItemNormalizer()._validate_modality("pdf")
            'pdf'
        """
        if value in {"pdf", "word", "excel", "html", "image", "audio", "unknown"}:  # Match the built-in parsing pipeline.
            return value  # type: ignore[return-value]
        return "unknown"

    def _make_id(self, source: dict[str, Any] | None, path_value: Any = None) -> str:
        """Generate a default sample id.

        Business logic:
            1. Prefer the file name for file input.
            2. Use the line number for row-based input.
            3. Use the current nanosecond timestamp when source information is insufficient.

        Args:
            source (dict[str, Any] | None): Input-source metadata.
            path_value (Any): Path field from user input.

        Returns:
            str: Sample id.

        Examples:
            >>> DataItemNormalizer()._make_id({"line": 2}).startswith("sample_2")
            True
        """
        if path_value not in (None, ""):  # Use the stem to keep behavior aligned with existing directory input.
            return _pure_path(path_value).stem
        source = source or {}
        if source.get("line") is not None:  # Use the line number to generate a stable sample name.
            return f"sample_{source['line']}"
        return f"sample_{time.time_ns()}"


class InputAdapter:
    def __init__(self, input_config: dict[str, Any], base_dir: Path | None = None) -> None:
        """Create a parsing input adapter.

        Business logic:
            1. Store workflow input configuration.
            2. Store the base directory used to resolve relative paths.
            3. Initialize the DataItem normalizer.

        Args:
            input_config (dict[str, Any]): Workflow input configuration.
            base_dir (Path | None): Base directory for resolving relative paths.

        Returns:
            None: The initializer does not return business data.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).input_config["type"]
            'raw_text'
        """
        self.input_config = input_config  # Input config: workflow input section.
        self.base_dir = base_dir or Path.cwd()  # Input config: base directory for resolving relative paths.
        self.normalizer = DataItemNormalizer(input_config)  # Input config: reuse DataItem normalization rules.

    def read(self) -> Iterable[DataItem]:
        """Read input and yield DataItem objects.

        Business logic:
            1. Resolve the actual input type.
            2. Dispatch to the corresponding reader by type.
            3. Yield normalized DataItem objects one by one.

        Args:
            None: No input arguments.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

        Examples:
            >>> list(InputAdapter({"type": "raw_text", "text": "x"}).read())[0].payload["text"]
            'x'
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # Configuration text becomes a single sample directly.
            yield self.normalizer.normalize({"text": str(self.input_config.get("text", ""))}, {"type": "raw_text"})
            return
        if input_type == "stdin":  # Standard input does not require a path.
            yield from self._read_stdin()
            return
        path = self._required_path()
        if input_type in {"file_dir", "directory"}:  # Keep compatibility with existing file_dir directory input.
            yield from self._read_directory(path)
        elif input_type == "file":  # Read a single file by extension.
            yield from self._read_file(path)
        elif input_type == "jsonl":  # Read JSONL line by line.
            yield from self._read_jsonl(path)
        elif input_type == "json":  # Read a JSON object or array.
            yield from self._read_json(path)
        elif input_type == "csv":  # Read CSV row by row.
            yield from self._read_csv(path)
        else:
            raise ValueError(f"unsupported input.type: {input_type}")

    def validate_config(self) -> None:
        """Validate input configuration.

        Business logic:
            1. Check whether input.type is supported.
            2. Check required fields for raw_text, stdin, and path-based input.
            3. Check path existence and directory/file type.

        Args:
            None: No input arguments.

        Returns:
            None: Raises an exception when validation fails.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).validate_config()
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # raw_text must provide text.
            if "text" not in self.input_config:  # A sample cannot be constructed without text.
                raise ValueError("input.text is required when input.type=raw_text")
            return
        if input_type == "stdin":  # stdin is read lazily at runtime.
            return
        path = self._required_path()
        if not path.exists():  # Path-based input must exist.
            raise FileNotFoundError(f"Input path does not exist: {path}")
        if input_type in {"file_dir", "directory"} and not path.is_dir():  # Directory input types must point to a directory.
            raise ValueError(f"input.path must be a directory when input.type={input_type}: {path}")
        if input_type not in {"file_dir", "directory"} and path.is_dir():  # Non-directory input types cannot point to a directory.
            raise ValueError(f"input.path must be a file when input.type={input_type}: {path}")

    def _resolve_input_type(self) -> str:
        """Resolve the actual input type.

        Business logic:
            1. Read input.type and default to auto when it is missing.
            2. Return explicit types directly.
            3. Infer auto from path or text.

        Args:
            None: No input arguments.

        Returns:
            str: Actual input type.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"})._resolve_input_type()
            'raw_text'
        """
        configured = str(self.input_config.get("type", "auto"))
        if configured not in SUPPORTED_INPUT_TYPES:  # Only accept values from the supported set.
            raise ValueError(f"unsupported input.type: {configured}")
        if configured != "auto":  # Explicit declarations take priority.
            return configured
        if "text" in self.input_config and "path" not in self.input_config:  # Treat input as raw_text when only text is present.
            return "raw_text"
        path = self._required_path()
        if path.is_dir():  # Automatically recognize directory paths as file_dir.
            return "file_dir"
        suffix = path.suffix.lower()
        if suffix in JSONL_EXTENSIONS:  # Auto-detect JSONL by extension.
            return "jsonl"
        if suffix in JSON_EXTENSIONS:  # Auto-detect JSON by extension.
            return "json"
        if suffix in CSV_EXTENSIONS:  # Auto-detect CSV by extension.
            return "csv"
        return "file"

    def _required_path(self) -> Path:
        """Read and resolve input.path.

        Business logic:
            1. Check whether input.path is declared.
            2. Use absolute paths directly.
            3. Resolve relative paths against the configured base directory.

        Args:
            None: No input arguments.

        Returns:
            Path: Resolved path.

        Examples:
            >>> isinstance(InputAdapter({"type": "file", "path": "a.txt"})._required_path(), Path)
            True
        """
        if not self.input_config.get("path"):  # Path-based input must declare path.
            raise ValueError("input.path is required for path-based input types")
        path = Path(str(self.input_config["path"]))
        return path if path.is_absolute() else self.base_dir / path

    def _read_directory(self, path: Path) -> Iterable[DataItem]:
        """Read directory input.

        Business logic:
            1. Traverse non-hidden files in the directory in sorted order.
            2. Read media files through DataItem.from_path to preserve the existing parsing path.
            3. Read text and structured files through the loose-input pipeline.

        Args:
            path (Path): Input directory path.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_directory)
            True
        """
        for file_path in sorted(item for item in path.rglob("*") if item.is_file() and not item.name.startswith(".")):  # Sorting keeps output stable.
            if file_path.suffix.lower() in SUPPORTED_MEDIA_SUFFIXES | TEXT_EXTENSIONS | JSON_EXTENSIONS | JSONL_EXTENSIONS | CSV_EXTENSIONS:  # Read only supported formats.
                yield from self._read_file(file_path)

    def _read_file(self, path: Path) -> Iterable[DataItem]:
        """Read a single-file input.

        Business logic:
            1. Process existing media files as path-based samples.
            2. Delegate JSON, JSONL, and CSV files to the corresponding readers.
            3. Treat other text files as payload.text content.

        Args:
            path (Path): Input file path.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_file)
            True
        """
        suffix = path.suffix.lower()
        if suffix in SUPPORTED_MEDIA_SUFFIXES:  # Preserve existing DataItem.from_path behavior.
            yield DataItem.from_path(path)
        elif suffix in JSON_EXTENSIONS:
            yield from self._read_json(path)
        elif suffix in JSONL_EXTENSIONS:
            yield from self._read_jsonl(path)
        elif suffix in CSV_EXTENSIONS:
            yield from self._read_csv(path)
        else:
            yield self.normalizer.normalize({"id": path.stem, "text": path.read_text(encoding="utf-8")}, {"type": "file", "path": str(path)})

    def _read_jsonl(self, path: Path) -> Iterable[DataItem]:
        """Read JSONL input.

        Business logic:
            1. Read line by line and skip empty lines.
            2. Parse each line as a JSON object.
            3. Normalize each record into a DataItem.

        Args:
            path (Path): JSONL path.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_jsonl)
            True
        """
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):  # Line numbers are kept for source auditing.
                if not line.strip():  # Empty lines do not produce samples.
                    continue
                yield self.normalizer.normalize(json.loads(line), {"type": "jsonl", "path": str(path), "line": line_no})

    def _read_json(self, path: Path) -> Iterable[DataItem]:
        """Read JSON object or array input.

        Business logic:
            1. Parse the JSON file.
            2. Treat arrays as multiple records.
            3. Treat a single object as one record.

        Args:
            path (Path): JSON path.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_json)
            True
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Array order determines sample order.
            yield self.normalizer.normalize(raw, {"type": "json", "path": str(path), "line": index})

    def _read_csv(self, path: Path) -> Iterable[DataItem]:
        """Read CSV input.

        Business logic:
            1. Read rows by header using DictReader.
            2. Use each row's fields as the source for a DataItem.
            3. Normalize each row into a DataItem.

        Args:
            path (Path): CSV path.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_csv)
            True
        """
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):  # Each row after the header corresponds to one sample.
                yield self.normalizer.normalize(dict(row), {"type": "csv", "path": str(path), "line": line_no})

    def _read_stdin(self) -> Iterable[DataItem]:
        """Read standard input.

        Business logic:
            1. Read the full content of sys.stdin.
            2. Try to parse it as a JSON object or array.
            3. Fall back to plain-text handling when parsing fails.

        Args:
            None: No input arguments.

        Returns:
            Iterable[DataItem]: Iterator of standard parsing samples.

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
