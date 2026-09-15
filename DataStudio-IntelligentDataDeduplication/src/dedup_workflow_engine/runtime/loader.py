from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _validated_path_value(path_value: str, name: str = "path") -> str:
    """Validate a configured path value before turning it into a Path."""
    text = str(path_value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if "\x00" in text or any(ord(char) < 32 for char in text):
        raise ValueError(f"{name} contains unsupported control characters")
    return text


def load_workflow_config(path: Path) -> dict[str, Any]:
    """Load a JSON or YAML workflow config.

    Business logic:
        1. Read the configuration file text.
        2. Detect a JSON object config from the first non-whitespace character.
        3. Otherwise parse it with PyYAML and verify the root object is a mapping.

    Args:
        path (Path): Workflow config file path.

    Returns:
        dict[str, Any]: Parsed workflow configuration dictionary.

    Raises:
        RuntimeError: Raised when YAML is used but PyYAML is not installed.
        ValueError: Raised when the config root object is not a mapping.

    Examples:
        >>> load_workflow_config(Path("workflow.json"))  # doctest: +SKIP
        {'workflow': {'id': 'demo'}}
    """
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("{"):  # JSON workflows are detected by their object opening brace.
        return json.loads(text)

    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required for YAML workflow files. Run `uv sync` in the project root as described in README.md."
        ) from exc

    data = yaml.safe_load(text)
    if not isinstance(data, dict):  # Workflow files must have named sections such as workflow, input, output, and steps.
        raise ValueError(f"Workflow config must be a mapping: {path}")
    return data


def resolve_path(path_value: str, base_dir: Path | None = None) -> Path:
    """Resolve a path declared in workflow config.

    Business logic:
        1. Convert the config string into a Path.
        2. Keep absolute paths unchanged.
        3. Join relative paths under base_dir or the current working directory.

    Args:
        path_value (str): Path string declared in workflow config.
        base_dir (Path | None, optional): Base directory for resolving relative paths. Defaults to the current directory.

    Returns:
        Path: Resolved Path object.

    Examples:
        >>> resolve_path("data/input.jsonl", Path("/tmp"))
        PosixPath('/tmp/data/input.jsonl')
    """
    path = Path(_validated_path_value(path_value)).expanduser()
    if path.is_absolute():  # Absolute workflow paths should be honored exactly.
        return path.resolve()
    return ((base_dir or Path.cwd()) / path).resolve()
