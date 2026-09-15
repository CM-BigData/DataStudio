from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from denoise_workflow_engine.runtime.loader import resolve_path


SUPPORTED_INPUT_TYPES = {"auto", "jsonl", "json", "csv", "directory", "file", "stdin", "raw_text"}  # Supported workflow input types.
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}  # File extensions treated as text content.
JSON_EXTENSIONS = {".json"}  # File extensions parsed as JSON files.
JSONL_EXTENSIONS = {".jsonl", ".ndjson"}  # File extensions parsed as JSONL files.
CSV_EXTENSIONS = {".csv"}  # File extensions parsed as CSV tables.
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}  # File extensions routed as image paths.
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv"}  # File extensions routed as video paths.
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}  # File extensions routed as audio paths.


class DataItemNormalizer:
    FILE_PAYLOAD_FIELDS = {"image_path", "video_path", "audio_path", "reference_image_path", "text_file"}

    def __init__(
        self,
        input_config: dict[str, Any] | None = None,
        path_resolver: Callable[[str, dict[str, Any] | None], Path] | None = None,
    ) -> None:
        """Create a normalizer for flexible user input.

        Business logic:
            1. Store field mappings from the input configuration.
            2. Normalize core fields using configured mappings and common fallback names.
            3. Fill workflow-required fields for every sample.

        Args:
            input_config (dict[str, Any] | None): Input configuration and field mappings.

        Returns:
            None: The constructor initializes the normalizer in place.

        Examples:
            >>> DataItemNormalizer({"text_field": "content"}).input_config["text_field"]
            'content'
        """
        self.input_config = input_config or {}  # Store field mappings and input reading settings.
        self.path_resolver = path_resolver

    def normalize(self, raw_item: Any, source: dict[str, Any] | None = None) -> dict[str, Any]:
        """Normalize flexible user input into a standard DataItem.

        Business logic:
            1. Accept either a mapping object or a raw text-like value.
            2. Detect ID, modality, payload, and common content fields.
            3. Fill workflow execution fields and preserve input source metadata.

        Args:
            raw_item (Any): One raw sample extracted from user input.
            source (dict[str, Any] | None): Input source metadata.

        Returns:
            dict[str, Any]: Normalized DataItem.

        Examples:
            >>> DataItemNormalizer().normalize("hello")["payload"]["text"]
            'hello'
        """
        if isinstance(raw_item, dict):  # Keep original fields from mapping objects for normalization.
            raw = dict(raw_item)
        else:
            raw = {"text": "" if raw_item is None else str(raw_item)}

        payload = raw.get("payload")
        if isinstance(payload, dict):  # Preserve the existing payload when it is already provided.
            payload_data = dict(payload)
            for key, value in raw.items():  # Merge top-level business fields into the payload.
                if key not in {"id", "modality", "payload", "meta", "intermediate", "metrics", "issues", "operator_trace", "action"}:  # Skip workflow control fields.
                    payload_data.setdefault(key, value)
        else:
            payload_data = {
                key: value
                for key, value in raw.items()
                if key not in {"id", "modality", "meta", "intermediate", "metrics", "issues", "operator_trace", "action"}
            }

        self._copy_mapped_field(raw, payload_data, "text_field", "text", ["text", "content", "body", "prompt", "description"])
        self._copy_mapped_field(raw, payload_data, "image_field", "image_path", ["image_path", "image", "img_path", "path"])
        self._copy_mapped_field(raw, payload_data, "video_field", "video_path", ["video_path", "video"])
        self._copy_mapped_field(raw, payload_data, "audio_field", "audio_path", ["audio_path", "audio"])

        item_id = self._read_mapped_value(raw, "id_field", ["id", "sample_id", "uid"])
        item = {
            "id": str(item_id) if item_id not in (None, "") else self._make_id(source),
            "modality": str(self._read_mapped_value(raw, "modality_field", ["modality", "type"]) or "unknown"),
            "payload": payload_data,
            "meta": dict(raw.get("meta", {})) if isinstance(raw.get("meta"), dict) else {},
            "intermediate": dict(raw.get("intermediate", {})) if isinstance(raw.get("intermediate"), dict) else {},
            "metrics": dict(raw.get("metrics", {})) if isinstance(raw.get("metrics"), dict) else {},
            "issues": list(raw.get("issues", [])) if isinstance(raw.get("issues"), list) else [],
            "operator_trace": list(raw.get("operator_trace", [])) if isinstance(raw.get("operator_trace"), list) else [],
            "action": str(raw.get("action") or "pending"),
        }
        item["meta"].setdefault("input_source", source or {})
        if item["modality"] == "unknown":  # Infer modality from payload when it is not declared explicitly.
            item["modality"] = self._infer_modality(item["payload"])
        if self.path_resolver is not None:
            for field in self.FILE_PAYLOAD_FIELDS:
                value = item["payload"].get(field)
                if value not in (None, ""):
                    item["payload"][field] = str(self.path_resolver(str(value), source))
        return item

    def _copy_mapped_field(
        self, raw: dict[str, Any], payload: dict[str, Any], config_key: str, target_key: str, candidates: list[str]
    ) -> None:
        """Copy a core payload field using configured mapping rules.

        Business logic:
            1. Prefer an explicit field mapping from the input configuration.
            2. Fall back to common candidate field names when no mapping is configured.
            3. Write the normalized target field only when it is still missing.

        Args:
            raw (dict[str, Any]): Raw sample fields.
            payload (dict[str, Any]): Payload dictionary to fill.
            config_key (str): Field mapping config key.
            target_key (str): Standardized payload field name.
            candidates (list[str]): Common fallback field names.

        Returns:
            None: The method mutates `payload` in place.

        Examples:
            >>> p = {}
            >>> DataItemNormalizer({"text_field": "content"})._copy_mapped_field({"content": "x"}, p, "text_field", "text", [])
            >>> p["text"]
            'x'
        """
        if target_key in payload and payload[target_key] not in (None, ""):  # Do not overwrite an already normalized field.
            return
        value = self._read_mapped_value(raw, config_key, candidates)
        if value not in (None, ""):  # Write only when a usable value is found.
            payload[target_key] = value

    def _read_mapped_value(self, raw: dict[str, Any], config_key: str, candidates: list[str]) -> Any:
        """Read a value from explicit mappings or fallback candidate fields.

        Business logic:
            1. Check the input configuration for an explicit field mapping first.
            2. Then check common field names in the raw object and payload.
            3. Return `None` when nothing matches.

        Args:
            raw (dict[str, Any]): Raw sample fields.
            config_key (str): Field mapping config key.
            candidates (list[str]): Common fallback field names.

        Returns:
            Any: Matched field value or `None`.

        Examples:
            >>> DataItemNormalizer({"id_field": "sample"})._read_mapped_value({"sample": "1"}, "id_field", [])
            '1'
        """
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        keys = [self.input_config.get(config_key), *candidates]
        for key in keys:  # Search explicit mappings before fallback candidates.
            if not key:  # Skip empty or missing field names.
                continue
            if key in raw:  # Prefer top-level fields.
                return raw[key]
            if key in payload:  # Then fall back to payload fields.
                return payload[key]
        return None

    def _infer_modality(self, payload: dict[str, Any]) -> str:
        """Infer sample modality from payload fields.

        Business logic:
            1. Return `image_text_pair` when both text and image are present.
            2. Return the matching single modality for video, image, audio, or text.
            3. Return `unknown` when no modality can be inferred.

        Args:
            payload (dict[str, Any]): Normalized payload.

        Returns:
            str: Inferred modality name.

        Examples:
            >>> DataItemNormalizer()._infer_modality({"text": "x"})
            'text'
        """
        has_text = bool(payload.get("text"))
        has_image = bool(payload.get("image_path"))
        if has_text and has_image:  # Text and image together form an image-text pair sample.
            return "image_text_pair"
        if payload.get("video_path"):  # Video path takes precedence over plain text inference.
            return "video"
        if has_image:  # Any image path implies image modality.
            return "image"
        if payload.get("audio_path"):  # Any audio path implies audio modality.
            return "audio"
        if has_text:  # Text alone implies text modality.
            return "text"
        return "unknown"

    def _make_id(self, source: dict[str, Any] | None) -> str:
        """Generate a stable readable ID for samples missing one.

        Business logic:
            1. Prefer line numbers or file names from the source metadata.
            2. Fall back to the current nanosecond timestamp when source data is insufficient.
            3. Return a string ID suitable for outputs and checkpoints.

        Args:
            source (dict[str, Any] | None): Input source metadata.

        Returns:
            str: Generated sample ID.

        Examples:
            >>> DataItemNormalizer()._make_id({"line": 2}).startswith("sample_2")
            True
        """
        source = source or {}
        if source.get("line") is not None:  # Prefer source line numbers for traceability.
            return f"sample_{source['line']}"
        if source.get("path"):  # Use the file stem as the default ID for file-based input.
            return Path(str(source["path"])).stem
        return f"sample_{time.time_ns()}"


class InputAdapter:
    def __init__(
        self,
        input_config: dict[str, Any],
        base_dir: Path | None = None,
        allowed_roots: Sequence[Path] | None = None,
    ) -> None:
        """Create an adapter that reads user input into workflow samples.

        Business logic:
            1. Store the input configuration and relative path base directory.
            2. Initialize the DataItemNormalizer.
            3. Dispatch to concrete readers based on `input.type` during `read`.

        Args:
            input_config (dict[str, Any]): Workflow input configuration.
            base_dir (Path | None): Base directory for resolving relative paths.

        Returns:
            None: The constructor initializes the adapter in place.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).input_config["type"]
            'raw_text'
        """
        self.input_config = input_config  # Store the workflow input section.
        self.base_dir = base_dir or Path.cwd()  # Base directory used to resolve relative paths.
        self.allowed_roots = tuple(allowed_roots) if allowed_roots is not None else None
        path_resolver = self._resolve_record_path if self.allowed_roots is not None else None
        self.normalizer = DataItemNormalizer(input_config, path_resolver=path_resolver)  # Reuse the same normalization rules across all reads.

    def _resolve_record_path(self, value: str, source: dict[str, Any] | None = None) -> Path:
        """Resolve a file path embedded in one input record under authorized roots."""
        project_dir = self.base_dir.parent if self.base_dir.name == "workflows" else self.base_dir
        candidates = [self.base_dir]
        if project_dir != self.base_dir:
            candidates.append(project_dir)
        if Path.cwd() not in candidates:
            candidates.append(Path.cwd())

        resolved_candidates = [
            resolve_path(value, base, allowed_roots=self.allowed_roots, name="record file path")
            for base in candidates
        ]
        for candidate in resolved_candidates:
            if candidate.exists():
                return candidate
        return resolved_candidates[0]

    def read(self) -> Iterable[dict[str, Any]]:
        """Read user input and yield standardized DataItem records.

        Business logic:
            1. Validate that `input.type` is supported.
            2. Infer the actual reader when `auto` mode is used.
            3. Yield normalized DataItem objects one by one.

        Args:
            None: This method does not take input parameters.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> list(InputAdapter({"type": "raw_text", "text": "x"}).read())[0]["payload"]["text"]
            'x'
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # Convert configured text directly into a text sample.
            yield self.normalizer.normalize({"text": str(self.input_config.get("text", ""))}, {"type": "raw_text"})
            return
        if input_type == "stdin":  # Standard input does not require a path.
            yield from self._read_stdin()
            return
        path = self._required_path()
        if input_type == "jsonl":  # Read JSONL line by line.
            yield from self._read_jsonl(path)
        elif input_type == "json":  # Read a JSON object or array.
            yield from self._read_json(path)
        elif input_type == "csv":  # Read CSV rows.
            yield from self._read_csv(path)
        elif input_type == "directory":  # Traverse all supported files under a directory.
            yield from self._read_directory(path)
        elif input_type == "file":  # Read a single file based on its extension.
            yield from self._read_file(path)
        else:
            raise ValueError(f"unsupported input.type: {input_type}")

    def validate_config(self) -> None:
        """Validate whether the input configuration satisfies reader requirements.

        Business logic:
            1. Check whether `input.type` is supported.
            2. Validate required fields for raw text, stdin, and path-based input.
            3. Verify path existence and type compatibility.

        Args:
            None: This method does not take input parameters.

        Returns:
            None: Raises `ValueError` or `FileNotFoundError` when validation fails.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).validate_config()
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # Raw text input must provide the `text` field.
            if "text" not in self.input_config:  # Text content is required to construct a sample.
                raise ValueError("input.text is required when input.type=raw_text")
            return
        if input_type == "stdin":  # Standard input is read lazily at runtime.
            return
        path = self._required_path()
        if not path.exists():  # Path-based input must point to an existing path.
            raise FileNotFoundError(f"Input path does not exist: {path}")
        if input_type == "directory" and not path.is_dir():  # Directory input must point to a directory.
            raise ValueError(f"input.path must be a directory when input.type=directory: {path}")
        if input_type != "directory" and path.is_dir():  # Non-directory input types must not point to directories.
            raise ValueError(f"input.path must be a file when input.type={input_type}: {path}")

    def _resolve_input_type(self) -> str:
        """Resolve the effective input type.

        Business logic:
            1. Read `input.type`, defaulting to `auto` when it is missing.
            2. Return explicit non-auto types after validation.
            3. Infer the type from path shape and file extension when auto mode is used.

        Args:
            None: This method does not take input parameters.

        Returns:
            str: Effective input type.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"})._resolve_input_type()
            'raw_text'
        """
        configured = str(self.input_config.get("type", "auto"))
        if configured not in SUPPORTED_INPUT_TYPES:  # Allow only declared supported input types.
            raise ValueError(f"unsupported input.type: {configured}")
        if configured != "auto":  # Explicit types take precedence over auto-detection.
            return configured
        if "text" in self.input_config and "path" not in self.input_config:  # Treat plain configured text as raw text input.
            return "raw_text"
        path = self._required_path()
        if path.is_dir():  # Directories are read with the directory reader.
            return "directory"
        suffix = path.suffix.lower()
        if suffix in JSONL_EXTENSIONS:  # Auto-detect JSONL by extension.
            return "jsonl"
        if suffix in JSON_EXTENSIONS:  # Auto-detect JSON by extension.
            return "json"
        if suffix in CSV_EXTENSIONS:  # Auto-detect CSV by extension.
            return "csv"
        return "file"

    def _required_path(self) -> Path:
        """Read and resolve `input.path`.

        Business logic:
            1. Confirm that `input.path` is configured.
            2. Resolve relative paths against the workflow base directory.
            3. Return a `Path` object for downstream readers.

        Args:
            None: This method does not take input parameters.

        Returns:
            Path: Resolved input path.

        Examples:
            >>> isinstance(InputAdapter({"type": "file", "path": "a.txt"})._required_path(), Path)
            True
        """
        if not self.input_config.get("path"):  # Path-based input types must declare `path`.
            raise ValueError("input.path is required for path-based input types")
        return resolve_path(
            str(self.input_config["path"]),
            self.base_dir,
            allowed_roots=self.allowed_roots,
            name="input path",
        )

    def _read_jsonl(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSONL input one line at a time.

        Business logic:
            1. Skip blank lines.
            2. Normalize successfully parsed JSON lines into DataItem objects.
            3. Create `invalid_json` review samples when parsing fails.

        Args:
            path (Path): JSONL file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_jsonl)
            True
        """
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):  # Keep source line numbers for error traceability.
                text = line.strip()
                if not text:  # Blank JSONL lines do not produce samples.
                    continue
                source = {"type": "jsonl", "path": str(path), "line": line_no}
                try:
                    raw = json.loads(text)
                    yield self.normalizer.normalize(raw, source)
                except json.JSONDecodeError as exc:
                    yield self.normalizer.normalize(
                        {
                            "id": f"invalid_json_line_{line_no}",
                            "payload": {"raw": text},
                            "issues": ["invalid_json"],
                            "action": "review",
                            "error": str(exc),
                        },
                        source,
                    )

    def _read_json(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read JSON object or array input.

        Business logic:
            1. Parse the entire JSON file.
            2. Treat arrays as multiple samples and objects as a single sample.
            3. Normalize each parsed row into a DataItem.

        Args:
            path (Path): JSON file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_json)
            True
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Preserve array order when emitting JSON samples.
            yield self.normalizer.normalize(raw, {"type": "json", "path": str(path), "line": index})

    def _read_csv(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read CSV input and emit samples row by row.

        Business logic:
            1. Read each row with `csv.DictReader`.
            2. Move row fields into the payload and normalize core fields through mappings.
            3. Record CSV line numbers in the source metadata for traceability.

        Args:
            path (Path): CSV file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_csv)
            True
        """
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):  # The first data row starts after the header.
                yield self.normalizer.normalize(dict(row), {"type": "csv", "path": str(path), "line": line_no})

    def _read_directory(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read supported files from a directory recursively.

        Business logic:
            1. Recursively traverse files and sort them for reproducibility.
            2. Skip files with unsupported extensions.
            3. Delegate each supported file to `_read_file`.

        Args:
            path (Path): Input directory path.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_directory)
            True
        """
        files: list[Path] = []
        for item in path.rglob("*"):
            file_path = (
                resolve_path(item, allowed_roots=self.allowed_roots, name="input file")
                if self.allowed_roots is not None
                else item
            )
            if file_path.is_file():
                files.append(file_path)
        for file_path in sorted(files):  # Sort traversal to keep output stable.
            if self._file_modality(file_path) == "unknown":  # Skip files whose modality cannot be recognized.
                continue
            yield from self._read_file(file_path)

    def _read_file(self, path: Path) -> Iterable[dict[str, Any]]:
        """Read a single file input.

        Business logic:
            1. Read text files into `payload.text`.
            2. Write image, video, and audio files into their path fields.
            3. Preserve unknown files as path-only samples with `unknown` modality.

        Args:
            path (Path): Input file path.

        Returns:
            Iterable[dict[str, Any]]: Iterator that yields the normalized sample(s).

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_file)
            True
        """
        modality = self._file_modality(path)
        source = {"type": "file", "path": str(path)}
        if modality == "text":  # Read plain text files into the text payload.
            yield self.normalizer.normalize({"id": path.stem, "modality": "text", "payload": {"text": path.read_text(encoding="utf-8")}}, source)
        elif modality == "image":  # Preserve image files as image paths.
            yield self.normalizer.normalize({"id": path.stem, "modality": "image", "payload": {"image_path": str(path)}}, source)
        elif modality == "video":  # Preserve video files as video paths.
            yield self.normalizer.normalize({"id": path.stem, "modality": "video", "payload": {"video_path": str(path)}}, source)
        elif modality == "audio":  # Preserve audio files as audio paths.
            yield self.normalizer.normalize({"id": path.stem, "modality": "audio", "payload": {"audio_path": str(path)}}, source)
        elif path.suffix.lower() in JSON_EXTENSIONS:  # Delegate JSON files to the JSON reader.
            yield from self._read_json(path)
        elif path.suffix.lower() in JSONL_EXTENSIONS:  # Delegate JSONL files to the JSONL reader.
            yield from self._read_jsonl(path)
        elif path.suffix.lower() in CSV_EXTENSIONS:  # Delegate CSV files to the CSV reader.
            yield from self._read_csv(path)
        else:
            yield self.normalizer.normalize({"id": path.stem, "modality": "unknown", "payload": {"path": str(path)}}, source)

    def _read_stdin(self) -> Iterable[dict[str, Any]]:
        """Read standard input.

        Business logic:
            1. Read the full stdin content.
            2. Try parsing it as a JSON object or array.
            3. Fall back to raw text when JSON parsing fails.

        Args:
            None: This method does not take input parameters.

        Returns:
            Iterable[dict[str, Any]]: Iterator of normalized samples.

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
        for index, raw in enumerate(rows, start=1):  # Preserve JSON array order for stdin input.
            yield self.normalizer.normalize(raw, {"type": "stdin", "line": index})

    def _file_modality(self, path: Path) -> str:
        """Infer file modality from its extension.

        Business logic:
            1. Read the file suffix and normalize it to lowercase.
            2. Match it against text, image, video, and audio extension sets.
            3. Return `unknown` when nothing matches.

        Args:
            path (Path): File path.

        Returns:
            str: File modality.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"})._file_modality(Path("a.txt"))
            'text'
        """
        suffix = path.suffix.lower()
        if suffix in TEXT_EXTENSIONS:  # Recognize text extensions.
            return "text"
        if suffix in IMAGE_EXTENSIONS:  # Recognize image extensions.
            return "image"
        if suffix in VIDEO_EXTENSIONS:  # Recognize video extensions.
            return "video"
        if suffix in AUDIO_EXTENSIONS:  # Recognize audio extensions.
            return "audio"
        return "unknown"
