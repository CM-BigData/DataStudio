from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import yaml

from synthesis_engine.models import GenerationItem, TaskType


SUPPORTED_INPUT_TYPES = {"auto", "seed_yaml", "jsonl", "json", "csv", "directory", "file", "stdin", "raw_text"}  # Supported workflow input-type set.
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".text"}  # File extensions that can be read as text prompts.
YAML_EXTENSIONS = {".yaml", ".yml"}  # File extensions that can be read as seed YAML.
JSON_EXTENSIONS = {".json"}  # File extensions that can be read as JSON.
JSONL_EXTENSIONS = {".jsonl", ".ndjson"}  # File extensions that can be read as JSONL.
CSV_EXTENSIONS = {".csv"}  # File extensions that can be read as CSV.


class GenerationItemNormalizer:
    def __init__(self, input_config: dict[str, Any] | None = None) -> None:
        """Create the generation-item normalizer

        Business logic:
            1. Store field mappings from the input configuration
            2. Convert flexible input objects into GenerationItem instances
            3. Preserve input-source metadata in lineage for auditing

        Args:
            input_config (dict[str, Any] | None): Workflow input configuration.

        Returns:
            None: Initializers do not return business data.

        Examples:
            >>> GenerationItemNormalizer({"prompt_field": "content"}).input_config["prompt_field"]
            'content'
        """
        self.input_config = input_config or {}  # Input configuration storing field mappings and read type.

    def normalize(self, raw_item: Any, source: dict[str, Any] | None = None) -> GenerationItem:
        """Convert flexible input into a GenerationItem

        Business logic:
            1. Accept dictionaries, strings, or other raw values
            2. Detect id, task_type, prompt, and payload
            3. Create a GenerationItem and write input_source lineage

        Args:
            raw_item (Any): One record split from user input.
            source (dict[str, Any] | None): Input-source metadata.

        Returns:
            GenerationItem: Normalized generation sample.

        Examples:
            >>> GenerationItemNormalizer().normalize("hello").prompt
            'hello'
        """
        raw = dict(raw_item) if isinstance(raw_item, dict) else {"prompt": "" if raw_item is None else str(raw_item)}
        payload = dict(raw.get("payload", {})) if isinstance(raw.get("payload"), dict) else {
            key: value
            for key, value in raw.items()
            if key not in {"id", "task_type", "prompt", "lineage", "generated", "metrics", "issues", "action"}
        }
        item_id = self._read_mapped_value(raw, "id_field", ["id", "sample_id", "uid"])
        task_type = str(self._read_mapped_value(raw, "task_type_field", ["task_type", "type"]) or "text")
        prompt = str(self._read_mapped_value(raw, "prompt_field", ["prompt", "text", "content", "instruction"]) or "")
        item = GenerationItem(
            id=str(item_id) if item_id not in (None, "") else self._make_id(source),
            task_type=self._validate_task_type(task_type),
            prompt=prompt,
            payload=payload,
            lineage=dict(raw.get("lineage", {})) if isinstance(raw.get("lineage"), dict) else {},
        )
        item.lineage.setdefault("seed_id", item.id)
        item.lineage.setdefault("created_at", item.lineage.get("created_at", ""))
        item.lineage["input_source"] = source or {}
        return item

    def _read_mapped_value(self, raw: dict[str, Any], config_key: str, candidates: list[str]) -> Any:
        """Read an explicit mapping or candidate field

        Business logic:
            1. Read the explicit field mapping from input config first
            2. Then try common candidate field names
            3. Return None when nothing matches

        Args:
            raw (dict[str, Any]): Raw record.
            config_key (str): Field-mapping config key.
            candidates (list[str]): Candidate field names.

        Returns:
            Any: Matched field value or None.

        Examples:
            >>> GenerationItemNormalizer({"id_field": "sample"})._read_mapped_value({"sample": "1"}, "id_field", [])
            '1'
        """
        keys = [self.input_config.get(config_key), *candidates]
        for key in keys:  # Search by explicit mapping first, then by candidate field names.
            if not key:  # Skip unset field names in the mapping list.
                continue
            if key in raw:  # Return immediately once the raw record contains the mapped field.
                return raw[key]
        return None

    def _validate_task_type(self, value: str) -> TaskType:
        """Validate and return the synthesis task type

        Business logic:
            1. Accept the task_type from user input
            2. Allow only the existing text, image, and structured task types
            3. Raise immediately on invalid values to avoid ambiguous operator routing

        Args:
            value (str): Task type from user input.

        Returns:
            TaskType: Valid task type.

        Examples:
            >>> GenerationItemNormalizer()._validate_task_type("text")
            'text'
        """
        if value not in {"text", "image", "structured"}:  # Task types must match the built-in operator domains.
            raise ValueError(f"unsupported task_type: {value}")
        return value  # type: ignore[return-value]

    def _make_id(self, source: dict[str, Any] | None) -> str:
        """Generate a fallback sample ID

        Business logic:
            1. Prefer the input-source line number
            2. Use the filename for file-based input
            3. Fall back to the current nanosecond timestamp when source data is insufficient

        Args:
            source (dict[str, Any] | None): Input-source metadata.

        Returns:
            str: Sample ID.

        Examples:
            >>> GenerationItemNormalizer()._make_id({"line": 2}).startswith("sample_2")
            True
        """
        source = source or {}
        if source.get("line") is not None:  # Prefer line numbers for line-based input sources.
            return f"sample_{source['line']}"
        if source.get("path"):  # Prefer filenames for file-based input sources.
            return Path(str(source["path"])).stem
        return f"sample_{time.time_ns()}"


class InputAdapter:
    def __init__(self, input_config: dict[str, Any], base_dir: Path | None = None) -> None:
        """Create the synthesis input adapter

        Business logic:
            1. Store the workflow input configuration
            2. Store the base directory for resolving relative paths
            3. Initialize the GenerationItem normalizer

        Args:
            input_config (dict[str, Any]): Workflow input configuration.
            base_dir (Path | None): Base directory for resolving relative paths.

        Returns:
            None: Initializers do not return business data.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).input_config["type"]
            'raw_text'
        """
        self.input_config = input_config  # Workflow input section configuration.
        self.base_dir = base_dir or Path.cwd()  # Base directory used to resolve relative paths.
        self.normalizer = GenerationItemNormalizer(input_config)  # Shared normalization rules for flexible input records.

    def read(self) -> Iterable[GenerationItem]:
        """Read input and yield GenerationItem objects

        Business logic:
            1. Resolve the effective input type
            2. Dispatch to the corresponding reader by type
            3. Yield normalized GenerationItem objects one by one

        Args:
            None: No input parameters.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> list(InputAdapter({"type": "raw_text", "text": "x"}).read())[0].prompt
            'x'
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # Convert configured text directly into a single prompt.
            yield self.normalizer.normalize({"prompt": str(self.input_config.get("text", "")), "task_type": "text"}, {"type": "raw_text"})
            return
        if input_type == "stdin":  # Standard input does not require a path.
            yield from self._read_stdin()
            return
        path = self._required_path()
        if input_type == "seed_yaml":  # Keep compatibility with existing seed_yaml inputs.
            yield from self._read_seed_yaml(path)
        elif input_type == "jsonl":  # Read JSONL line by line.
            yield from self._read_jsonl(path)
        elif input_type == "json":  # Read JSON objects or arrays.
            yield from self._read_json(path)
        elif input_type == "csv":  # Read CSV row by row.
            yield from self._read_csv(path)
        elif input_type == "directory":  # Read supported files under a directory.
            yield from self._read_directory(path)
        elif input_type == "file":  # Read a single file by its extension.
            yield from self._read_file(path)
        else:
            raise ValueError(f"unsupported input.type: {input_type}")

    def validate_config(self) -> None:
        """Validate the input configuration

        Business logic:
            1. Check whether input.type is supported
            2. Check required fields for raw_text, stdin, and path-based input
            3. Check path existence and directory-versus-file expectations

        Args:
            None: No input parameters.

        Returns:
            None: Raises an exception when validation fails.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"}).validate_config()
        """
        input_type = self._resolve_input_type()
        if input_type == "raw_text":  # raw_text must provide text.
            if "text" not in self.input_config:  # Missing text means no prompt can be constructed.
                raise ValueError("input.text is required when input.type=raw_text")
            return
        if input_type == "stdin":  # stdin is read lazily at runtime.
            return
        path = self._required_path()
        if not path.exists():  # Path-based input must exist.
            raise FileNotFoundError(f"Input path does not exist: {path}")
        if input_type == "directory" and not path.is_dir():  # Directory mode must point to a directory.
            raise ValueError(f"input.path must be a directory when input.type=directory: {path}")
        if input_type != "directory" and path.is_dir():  # Non-directory modes cannot point to a directory.
            raise ValueError(f"input.path must be a file when input.type={input_type}: {path}")

    def _resolve_input_type(self) -> str:
        """Resolve the effective input type

        Business logic:
            1. Read input.type and default to auto when missing
            2. Return explicit types directly
            3. Infer auto mode from path or text

        Args:
            None: No input parameters.

        Returns:
            str: Effective input type.

        Examples:
            >>> InputAdapter({"type": "raw_text", "text": "x"})._resolve_input_type()
            'raw_text'
        """
        configured = str(self.input_config.get("type", "auto"))
        if configured not in SUPPORTED_INPUT_TYPES:  # Accept only supported input types.
            raise ValueError(f"unsupported input.type: {configured}")
        if configured != "auto":  # Explicit declarations take priority.
            return configured
        if "text" in self.input_config and "path" not in self.input_config:  # Treat text-only config as raw_text.
            return "raw_text"
        path = self._required_path()
        if path.is_dir():  # Auto-detect directory paths as directory input.
            return "directory"
        suffix = path.suffix.lower()
        if suffix in YAML_EXTENSIONS:  # Treat YAML extensions as seed_yaml.
            return "seed_yaml"
        if suffix in JSONL_EXTENSIONS:  # Auto-detect JSONL extensions.
            return "jsonl"
        if suffix in JSON_EXTENSIONS:  # Auto-detect JSON extensions.
            return "json"
        if suffix in CSV_EXTENSIONS:  # Auto-detect CSV extensions.
            return "csv"
        return "file"

    def _required_path(self) -> Path:
        """Read and resolve input.path

        Business logic:
            1. Check whether input.path is declared
            2. Use absolute paths directly
            3. Resolve relative paths from the configured base directory

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
        path = Path(str(self.input_config["path"]))
        return path if path.is_absolute() else self.base_dir / path

    def _read_seed_yaml(self, path: Path) -> Iterable[GenerationItem]:
        """Read existing seed_yaml input

        Business logic:
            1. Read the YAML file
            2. Extract seed entries from the items list
            3. Convert them into GenerationItem instances

        Args:
            path (Path): Seed YAML path.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_seed_yaml)
            True
        """
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for index, item in enumerate(raw.get("items", []), start=1):  # Preserve item order because it defines sample order.
            yield self.normalizer.normalize(item, {"type": "seed_yaml", "path": str(path), "line": index})

    def _read_jsonl(self, path: Path) -> Iterable[GenerationItem]:
        """Read JSONL input

        Business logic:
            1. Read line by line and skip empty lines
            2. Parse each line as a JSON object
            3. Normalize each row into a GenerationItem

        Args:
            path (Path): JSONL path.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_jsonl)
            True
        """
        with path.open("r", encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):  # Keep line numbers for audit metadata.
                if not line.strip():  # Empty lines do not produce samples.
                    continue
                yield self.normalizer.normalize(json.loads(line), {"type": "jsonl", "path": str(path), "line": line_no})

    def _read_json(self, path: Path) -> Iterable[GenerationItem]:
        """Read JSON object or array input

        Business logic:
            1. Parse the JSON file
            2. Treat arrays as multiple records
            3. Treat objects as single records

        Args:
            path (Path): JSON path.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_json)
            True
        """
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Preserve array element order as sample order.
            yield self.normalizer.normalize(raw, {"type": "json", "path": str(path), "line": index})

    def _read_csv(self, path: Path) -> Iterable[GenerationItem]:
        """Read CSV input

        Business logic:
            1. Read rows with DictReader using the header
            2. Use each row as the payload source
            3. Normalize each row into a GenerationItem

        Args:
            path (Path): CSV path.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_csv)
            True
        """
        with path.open("r", encoding="utf-8", newline="") as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):  # The first row after the header maps to one sample.
                yield self.normalizer.normalize(dict(row), {"type": "csv", "path": str(path), "line": line_no})

    def _read_directory(self, path: Path) -> Iterable[GenerationItem]:
        """Read text-seed files inside a directory

        Business logic:
            1. Traverse supported files in sorted order
            2. Skip unrecognized extensions
            3. Delegate sample generation to the single-file reader

        Args:
            path (Path): Directory path.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_directory)
            True
        """
        for file_path in sorted(item for item in path.rglob("*") if item.is_file()):  # Sort directory input to keep output stable.
            if file_path.suffix.lower() not in TEXT_EXTENSIONS | YAML_EXTENSIONS | JSON_EXTENSIONS | JSONL_EXTENSIONS | CSV_EXTENSIONS:  # Read only supported formats from directory input.
                continue
            yield from self._read_file(file_path)

    def _read_file(self, path: Path) -> Iterable[GenerationItem]:
        """Read single-file input

        Business logic:
            1. Delegate YAML, JSON, JSONL, and CSV files to their corresponding readers
            2. Use text-file contents as the prompt
            3. Fall back to the file path as the prompt for other files

        Args:
            path (Path): File path.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "raw_text", "text": "x"})._read_file)
            True
        """
        suffix = path.suffix.lower()
        if suffix in YAML_EXTENSIONS:  # YAML files are compatible with seed_yaml input.
            yield from self._read_seed_yaml(path)
        elif suffix in JSON_EXTENSIONS:  # Delegate JSON files to the JSON reader.
            yield from self._read_json(path)
        elif suffix in JSONL_EXTENSIONS:  # Delegate JSONL files to the JSONL reader.
            yield from self._read_jsonl(path)
        elif suffix in CSV_EXTENSIONS:  # Delegate CSV files to the CSV reader.
            yield from self._read_csv(path)
        else:
            yield self.normalizer.normalize({"id": path.stem, "task_type": "text", "prompt": path.read_text(encoding="utf-8")}, {"type": "file", "path": str(path)})

    def _read_stdin(self) -> Iterable[GenerationItem]:
        """Read standard input

        Business logic:
            1. Read the full content of sys.stdin
            2. Try parsing it as a JSON object or array
            3. Fall back to treating it as a text prompt when parsing fails

        Args:
            None: No input parameters.

        Returns:
            Iterable[GenerationItem]: Iterator of normalized generation samples.

        Examples:
            >>> callable(InputAdapter({"type": "stdin"})._read_stdin)
            True
        """
        text = sys.stdin.read()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            yield self.normalizer.normalize({"task_type": "text", "prompt": text}, {"type": "stdin"})
            return
        rows = data if isinstance(data, list) else [data]
        for index, raw in enumerate(rows, start=1):  # Preserve JSON-array order for stdin samples.
            yield self.normalizer.normalize(raw, {"type": "stdin", "line": index})
