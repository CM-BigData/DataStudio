from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Callable, Iterable


SUPPORTED_INPUT_TYPES = {"auto", "jsonl", "json", "csv", "image_folder", "directory", "file", "stdin", "raw_text"}  # Supported input types accepted by workflow config.
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}  # Extensions that can be read into payload.text.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".ppm", ".pgm", ".tif", ".tiff"}  # Extensions that can be read into payload.image_path.
AUDIO_EXTENSIONS = {".wav", ".flac", ".mp3", ".m4a", ".aac", ".ogg", ".wma"}  # Extensions that can be read into payload.audio_path.
JSON_EXTENSIONS = {".json"}  # Extensions treated as JSON input.
JSONL_EXTENSIONS = {".jsonl", ".ndjson"}  # Extensions treated as JSONL input.
CSV_EXTENSIONS = {".csv"}  # Extensions treated as CSV input.


def _pure_stem(path_value: object) -> str:
    """Extract a filename stem without resolving the path on the filesystem."""
    text = str(path_value)
    return PureWindowsPath(text).stem if "\\" in text else PurePath(text).stem


class QualityItemNormalizer:
    FILE_PAYLOAD_FIELDS = {"image_path", "audio_path"}

    def __init__(
        self,
        workflow: dict[str, Any] | None = None,
        input_config: dict[str, Any] | None = None,
        path_resolver: Callable[[str], Path] | None = None,
    ) -> None:
        """Create the quality-evaluation sample normalizer.

        Business logic:
            1. Store task type and field mappings from workflow and input config.
            2. Convert strings, dictionaries, and other raw values into unified sample dicts.
            3. Preserve non-core fields in payload or meta for custom operators.

        Args:
            workflow (dict[str, Any] | None): Workflow config section.
            input_config (dict[str, Any] | None): Workflow input config section.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> QualityItemNormalizer({"task_type": "text"}).workflow["task_type"]
            'text'
        """
        self.workflow = workflow or {}  # Workflow config used for default task-type inference.
        self.input_config = input_config or {}  # Input config used for field mapping and type inference.
        self.path_resolver = path_resolver

    def normalize(self, raw_item: Any, source: dict[str, Any] | None = None) -> dict[str, Any]:
        """Convert flexible input into a quality-evaluation sample.

        Business logic:
            1. Accept dicts, strings, or other raw values.
            2. Identify id, modality, text, image_path, label, payload, and meta.
            3. Fill in source, intermediate, metrics, issues, and action fields.

        Args:
            raw_item (Any): One record after user input is split.
            source (dict[str, Any] | None): Input source metadata.

        Returns:
            dict[str, Any]: Standard sample that can enter the evaluation workflow.

        Examples:
            >>> QualityItemNormalizer({"task_type": "text"}).normalize("hello")["payload"]["text"]
            'hello'
        """
        raw = dict(raw_item) if isinstance(raw_item, dict) else {"text": "" if raw_item is None else str(raw_item)}
        payload = self._resolve_payload(raw)
        meta = dict(raw.get("meta", {})) if isinstance(raw.get("meta"), dict) else {}
        item_id = self._read_mapped_value(raw, "id_field", ["id", "sample_id", "uid"])
        modality = self._read_mapped_value(raw, "modality_field", ["modality", "type"])
        text_value = self._read_mapped_value(raw, "text_field", ["text", "content", "body"])
        is_audio_workflow = self.workflow.get("task_type") == "audio"
        image_candidates = ["image_path", "image"] if is_audio_workflow else ["image_path", "image", "path"]
        audio_candidates = ["audio_path", "audio", "path"] if is_audio_workflow else ["audio_path", "audio"]
        image_value = self._read_mapped_value(raw, "image_path_field", image_candidates)
        audio_value = self._read_mapped_value(raw, "audio_path_field", audio_candidates)
        label_value = self._read_mapped_value(raw, "label_field", ["label", "category", "class"])
        if text_value is not None:  # Normalize text content into payload.text.
            payload.setdefault("text", str(text_value))
        if image_value not in (None, "") and "text" not in payload:  # Prefer image workflow when an image path exists and text is absent.
            payload.setdefault("image_path", str(image_value))
        if audio_value not in (None, "") and "text" not in payload and "image_path" not in payload:  # Prefer audio workflow when an audio path exists and text/image is absent.
            payload.setdefault("audio_path", str(audio_value))
        if label_value is not None:  # Preserve label fields in meta for completeness operators.
            meta.setdefault("label", label_value)
            payload.setdefault("label", label_value)

        source_info = dict(raw.get("source", {})) if isinstance(raw.get("source"), dict) else {}
        source_info.update(source or {})
        missing_id = item_id in (None, "")
        if missing_id:  # Still generate a stable ID when missing, but preserve the original missing-ID fact for schema operators.
            meta.setdefault("_missing_id", True)
        item = {
            "id": str(item_id) if not missing_id else self._make_id(source_info, payload),
            "modality": self._infer_modality(str(modality or self.workflow.get("task_type", "unknown")), payload),
            "source": source_info,
            "payload": payload,
            "meta": meta,
            "intermediate": dict(raw.get("intermediate", {})) if isinstance(raw.get("intermediate"), dict) else {},
            "metrics": dict(raw.get("metrics", {})) if isinstance(raw.get("metrics"), dict) else {},
            "issues": list(raw.get("issues", [])) if isinstance(raw.get("issues"), list) else [],
            "action": str(raw.get("action", "pending")),
        }
        if self.path_resolver is not None:
            for field in self.FILE_PAYLOAD_FIELDS:
                value = item["payload"].get(field)
                if value not in (None, ""):
                    item["payload"][field] = str(self.path_resolver(str(value)))
        return item

    def _resolve_payload(self, raw: dict[str, Any]) -> dict[str, Any]:
        """Resolve payload from user input.

        Business logic:
            1. Prefer an explicit payload object.
            2. Preserve additional non-core fields as payload supplements.
            3. Avoid overwriting fields the user already put into payload.

        Args:
            raw (dict[str, Any]): Raw input record.

        Returns:
            dict[str, Any]: Normalized payload.

        Examples:
            >>> QualityItemNormalizer()._resolve_payload({"payload": {"a": 1}, "b": 2})["b"]
            2
        """
        payload = dict(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {}
        reserved = {"id", "sample_id", "uid", "modality", "type", "text", "content", "body", "path", "image", "image_path", "audio", "audio_path", "label", "category", "class", "payload", "meta", "source", "intermediate", "metrics", "issues", "action"}
        for key, value in raw.items():  # Preserve additional fields for custom-operator use.
            if key not in reserved and key not in payload:  # Avoid overwriting explicit payload fields.
                payload[key] = value
        return payload

    def _read_mapped_value(self, raw: dict[str, Any], config_key: str, candidates: list[str]) -> Any:
        """Read an explicitly mapped field or a candidate field.

        Business logic:
            1. Read the explicit field name from input config first.
            2. Then try common candidate field names.
            3. Return None when nothing matches.

        Args:
            raw (dict[str, Any]): Raw record.
            config_key (str): Field-mapping config key.
            candidates (list[str]): Candidate field-name list.

        Returns:
            Any: Matched field value or None.

        Examples:
            >>> QualityItemNormalizer(input_config={"id_field": "sid"})._read_mapped_value({"sid": "1"}, "id_field", [])
            '1'
        """
        keys = [self.input_config.get(config_key), *candidates]
        for key in keys:  # Explicit mappings take priority over default candidates.
            if key and key in raw:  # Return immediately after the first usable match.
                return raw[key]
        return None

    def _infer_modality(self, configured: str, payload: dict[str, Any]) -> str:
        """Infer sample modality.

        Business logic:
            1. Prefer valid explicit modality values.
            2. Infer from payload.text or payload.image_path.
            3. Return unknown when inference is impossible.

        Args:
            configured (str): Modality from user config or the record itself.
            payload (dict[str, Any]): Normalized payload.

        Returns:
            str: text, image, or unknown.

        Examples:
            >>> QualityItemNormalizer()._infer_modality("unknown", {"text": "x"})
            'text'
        """
        if configured in {"text", "image", "audio"}:  # Valid explicit modality takes priority.
            return configured
        if "text" in payload:  # Text fields route into text evaluation.
            return "text"
        if "image_path" in payload:  # Image paths route into image evaluation.
            return "image"
        if "audio_path" in payload:  # Audio paths route into audio evaluation.
            return "audio"
        return "unknown"

    def _make_id(self, source: dict[str, Any] | None, payload: dict[str, Any]) -> str:
        """Generate a fallback sample ID.

        Business logic:
            1. Prefer the filename when an image path exists.
            2. Use source path or line number for file or line-based inputs.
            3. Fall back to current nanosecond time when source info is insufficient.

        Args:
            source (dict[str, Any] | None): Input source metadata.
            payload (dict[str, Any]): Normalized payload.

        Returns:
            str: Sample ID.

        Examples:
            >>> QualityItemNormalizer()._make_id({"line_no": 2}, {}).startswith("sample_2")
            True
        """
        for media_key in ("image_path", "audio_path"):  # Media paths can provide stable filenames.
            if payload.get(media_key):
                return _pure_stem(payload[media_key])
        source = source or {}
        if source.get("path") and source.get("format") == "file":  # Text-file input uses the filename.
            return _pure_stem(source["path"])
        if source.get("line_no") is not None:  # Line numbers provide stable sample names.
            return f"sample_{source['line_no']}"
        if source.get("line") is not None:  # Support legacy line-field sources.
            return f"sample_{source['line']}"
        return f"sample_{time.time_ns()}"


class InputAdapter:
    def __init__(self, workflow: dict[str, Any], input_config: dict[str, Any], resolver: Any) -> None:
        """Create the quality-evaluation input adapter.

        Business logic:
            1. Store workflow, input config, and the path resolver.
            2. Initialize the quality-evaluation sample normalizer.
            3. Read and produce standard samples based on input.type.

        Args:
            workflow (dict[str, Any]): Workflow config section.
            input_config (dict[str, Any]): Workflow input config section.
            resolver (Any): Path resolver function.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> InputAdapter({"task_type": "text"}, {"type": "raw_text", "text": "x"}, lambda value: Path(value)).input_config["type"]
            'raw_text'
        """
        self.workflow = workflow  # Workflow config used for the default task type.
        self.input_config = input_config  # Workflow input section.
        self.resolver = resolver  # Path resolver reused from the executor path base.
        self.normalizer = QualityItemNormalizer(
            workflow,
            input_config,
            path_resolver=lambda value: Path(self.resolver(value)),
        )  # Reuse the dict-sample normalization rules from input config.

    def read(self) -> list[dict[str, Any]]:
        """Read input and produce quality-evaluation samples.

        Business logic:
            1. Resolve the actual input type.
            2. Dispatch to the concrete reader by type.
            3. Return the standard dict sample list.

        Args:
            None.

        Returns:
            list[dict[str, Any]]: Standard quality-evaluation sample list.

        Examples:
            >>> InputAdapter({"task_type": "text"}, {"type": "raw_text", "text": "x"}, lambda value: Path(value)).read()[0]["payload"]["text"]
            'x'
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # Configured text becomes a single sample directly.
            return [self.normalizer.normalize({"text": str(self.input_config.get("text", ""))}, {"format": "raw_text"})]
        if input_type == "stdin":  # Standard input does not require a path.
            return list(self._read_stdin())
        path = self._required_path()
        if input_type == "jsonl":  # Read JSONL line by line.
            return list(self._read_jsonl(path))
        if input_type == "json":  # Read JSON objects or arrays.
            return list(self._read_json(path))
        if input_type == "csv":  # Read CSV row by row.
            return list(self._read_csv(path))
        if input_type == "directory":  # Read directories by file extension.
            return list(self._read_directory(path))
        if input_type == "file":  # Read single files by extension.
            return list(self._read_file(path))
        raise ValueError(f"Unsupported input.type: {input_type}")

    def validate_config(self) -> None:
        """Validate input configuration.

        Business logic:
            1. Check whether input.type is supported.
            2. Check required fields for raw_text, stdin, and path-based inputs.
            3. Check path existence and directory/file type.

        Args:
            None.

        Returns:
            None: Raises an exception when validation fails.

        Examples:
            >>> InputAdapter({"task_type": "text"}, {"type": "raw_text", "text": "x"}, lambda value: Path(value)).validate_config()
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # raw_text must provide text.
            if "text" not in self.input_config:  # Samples cannot be built when text is missing.
                raise ValueError("input.text is required when input.type=raw_text")
            return
        if input_type == "stdin":  # stdin is read lazily at runtime.
            return
        if input_type == "image_folder":  # image_folder annotation is validated by the original DataReader.
            return
        path = self._required_path()
        if not path.exists():  # Path-based inputs must exist.
            raise FileNotFoundError(f"Input path does not exist: {path}")
        if input_type == "directory" and not path.is_dir():  # Directory input types must point to directories.
            raise ValueError(f"input.path must be a directory when input.type=directory: {path}")
        if input_type != "directory" and path.is_dir():  # Non-directory input types cannot point to directories.
            raise ValueError(f"input.path must be a file when input.type={input_type}: {path}")

    def _resolve_input_type(self) -> str:
        """Resolve the effective input type.

        Business logic:
            1. Read input.type and default to auto when it is missing.
            2. Return explicit types directly.
            3. Infer auto inputs from path or text fields.

        Args:
            None.

        Returns:
            str: Effective input type.

        Examples:
            >>> InputAdapter({"task_type": "text"}, {"type": "raw_text", "text": "x"}, lambda value: Path(value))._resolve_input_type()
            'raw_text'
        """
        configured = str(self.input_config.get("type", "auto"))
        if configured not in SUPPORTED_INPUT_TYPES:  # Accept only supported input types.
            raise ValueError(f"Unsupported input.type: {configured}")
        if configured != "auto":  # Explicit declarations take precedence.
            return configured
        if "text" in self.input_config and "path" not in self.input_config:  # Treat text-only input as raw_text.
            return "raw_text"
        path = self._required_path()
        if path.is_dir():  # Directory paths are inferred as directory inputs.
            return "directory"
        suffix = path.suffix.lower()
        if suffix in JSONL_EXTENSIONS:  # JSONL extensions are inferred automatically.
            return "jsonl"
        if suffix in JSON_EXTENSIONS:  # JSON extensions are inferred automatically.
            return "json"
        if suffix in CSV_EXTENSIONS:  # CSV extensions are inferred automatically.
            return "csv"
        return "file"

    def _required_path(self) -> Path:
        """Read and resolve input.path.

        Business logic:
            1. Check whether input.path is declared.
            2. Pass the path value to the executor resolver.
            3. Return the resolved path.

        Args:
            None.

        Returns:
            Path: Resolved path.

        Examples:
            >>> isinstance(InputAdapter({}, {"type": "file", "path": "a.txt"}, lambda value: Path(value))._required_path(), Path)
            True
        """
        if not self.input_config.get("path"):  # Path-based input types must declare path.
            raise ValueError("input.path is required for path-based input types")
        return Path(self.resolver(self.input_config["path"]))

    def _read_jsonl(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSONL input.

        Business logic:
            1. Read line by line and skip blank lines.
            2. Parse each line as a JSON object.
            3. Normalize records into quality-evaluation samples.

        Args:
            path (Path): JSONL path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({}, {"type": "raw_text", "text": "x"}, lambda value: Path(value))._read_jsonl)
            True
        """
        with path.open("r", encoding="utf-8-sig") as handle:
            for line_no, line in enumerate(handle, start=1):  # Line numbers support source auditing.
                if not line.strip():  # Blank lines do not produce samples.
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    raw = {"id": f"line_{line_no}", "text": "", "label": "", "_invalid_json": True}
                yield self.normalizer.normalize(raw, {"path": str(path), "format": "jsonl", "line_no": line_no})

    def _read_json(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSON object or array input.

        Business logic:
            1. Parse the JSON file.
            2. Treat arrays as multiple records.
            3. Treat objects as single records.

        Args:
            path (Path): JSON path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({}, {"type": "raw_text", "text": "x"}, lambda value: Path(value))._read_json)
            True
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Array order determines sample order.
            yield self.normalizer.normalize(raw, {"path": str(path), "format": "json", "line_no": index})

    def _read_csv(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read CSV input.

        Business logic:
            1. Use DictReader to read fields by header.
            2. Use each row's fields as the sample source.
            3. Normalize rows into quality-evaluation samples.

        Args:
            path (Path): CSV path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({}, {"type": "raw_text", "text": "x"}, lambda value: Path(value))._read_csv)
            True
        """
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):  # The row after the header corresponds to one sample.
                yield self.normalizer.normalize(dict(row), {"path": str(path), "format": "csv", "line_no": line_no})

    def _read_directory(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read directory input.

        Business logic:
            1. Traverse non-hidden files in sorted order.
            2. Generate text or image samples based on extensions.
            3. Delegate structured files to their matching readers.

        Args:
            path (Path): Input directory path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({}, {"type": "raw_text", "text": "x"}, lambda value: Path(value))._read_directory)
            True
        """
        files: list[Path] = []
        for item in path.rglob("*"):
            file_path = Path(self.resolver(item))
            if file_path.is_file() and not file_path.name.startswith("."):
                files.append(file_path)
        for file_path in sorted(files):  # Sorting keeps output stable.
            if file_path.suffix.lower() in TEXT_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | JSON_EXTENSIONS | JSONL_EXTENSIONS | CSV_EXTENSIONS:  # Read only supported formats.
                yield from self._read_file(file_path)

    def _read_file(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read single-file input.

        Business logic:
            1. Delegate JSON, JSONL, and CSV files to their matching readers.
            2. Read text-file content into payload.text.
            3. Read image-file paths into payload.image_path.

        Args:
            path (Path): Input file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({}, {"type": "raw_text", "text": "x"}, lambda value: Path(value))._read_file)
            True
        """
        suffix = path.suffix.lower()
        if suffix in JSON_EXTENSIONS:  # Delegate JSON files to the JSON reader.
            yield from self._read_json(path)
        elif suffix in JSONL_EXTENSIONS:  # Delegate JSONL files to the JSONL reader.
            yield from self._read_jsonl(path)
        elif suffix in CSV_EXTENSIONS:  # Delegate CSV files to the CSV reader.
            yield from self._read_csv(path)
        elif suffix in TEXT_EXTENSIONS:  # Read text-file content.
            yield self.normalizer.normalize({"id": path.stem, "text": path.read_text(encoding="utf-8")}, {"path": str(path), "format": "file"})
        elif suffix in IMAGE_EXTENSIONS:  # Read image-file paths.
            yield self.normalizer.normalize({"id": path.stem, "modality": "image", "payload": {"image_path": str(path)}}, {"path": str(path), "format": "file"})
        elif suffix in AUDIO_EXTENSIONS:  # Read audio-file paths.
            yield self.normalizer.normalize({"id": path.stem, "modality": "audio", "payload": {"audio_path": str(path)}}, {"path": str(path), "format": "file"})
        else:
            yield self.normalizer.normalize({"id": path.stem, "payload": {"path": str(path)}}, {"path": str(path), "format": "file"})

    def _read_stdin(self) -> Iterable[dict[str, Any]]:
        """Read standard input.

        Business logic:
            1. Read the complete sys.stdin content.
            2. Try to parse it as a JSON object or array.
            3. Treat it as a text sample when parsing fails.

        Args:
            None.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({}, {"type": "stdin"}, lambda value: Path(value))._read_stdin)
            True
        """
        text = sys.stdin.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            yield self.normalizer.normalize({"text": text}, {"format": "stdin"})
            return
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Generate samples from JSON arrays in order.
            yield self.normalizer.normalize(raw, {"format": "stdin", "line_no": index})
