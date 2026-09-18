from __future__ import annotations

import json
import os
from pathlib import Path, PureWindowsPath
from typing import Any, Sequence


def _validated_path_value(path_value: str | Path, name: str = "path") -> str:
    """Validate a configured path value before path resolution."""
    text = str(path_value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if "\x00" in text or any(ord(char) < 32 for char in text):
        raise ValueError(f"{name} contains unsupported control characters")
    return text


def resolve_allowed_roots(
    values: Sequence[str | Path] | None = None,
    *,
    default_root: Path | None = None,
) -> tuple[Path, ...]:
    """Resolve existing directories that explicitly authorize path access."""
    roots: list[Path] = []
    for value in (default_root or Path.cwd(), *(values or [])):
        text = os.path.expanduser(_validated_path_value(value, "allow-root"))
        root = Path.cwd().joinpath(text).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("allow-root must be an existing directory")
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def load_workflow_config(path: Path) -> dict[str, Any]:
    """Load a workflow configuration from JSON or YAML.

    Business logic:
        1. Read the configuration file content from disk.
        2. Parse JSON directly when the content starts with `{`.
        3. Fall back to YAML parsing and validate that the result is a mapping.

    Args:
            path (Path): Configuration file path.

    Returns:
        dict[str, Any]: Parsed workflow configuration mapping.

    Examples:
        >>> callable(load_workflow_config)
        True
    """
    text = path.read_text(encoding="utf-8")
    stripped = text.lstrip()
    if stripped.startswith("{"):  # Parse as JSON when the file starts with a left brace.
        return json.loads(text)

    try:
        import yaml  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required for non-JSON YAML files. Run `uv sync` in the project root as described in README.md."
        ) from exc

    data = yaml.safe_load(text)
    if not isinstance(data, dict):  # Reject non-mapping workflow definitions.
        raise ValueError(f"Workflow config must be a mapping: {path}")
    return data


def resolve_path(
    path_value: str | Path,
    base_dir: Path | None = None,
    *,
    allowed_roots: Sequence[Path] | None = None,
    name: str = "path",
) -> Path:
    """Resolve a configured path against the workflow base directory.

    Business logic:
        1. Read the configured path string.
        2. Return it unchanged when it is already absolute.
        3. Otherwise resolve it relative to the provided base directory or the current working directory.

    Args:
            path_value (str): Configured path string.
            base_dir (Path | None): Base directory for relative paths.

    Returns:
        Path: Resolved path object.

    Examples:
        >>> resolve_path("a.txt", Path("/tmp"))
        PosixPath('/tmp/a.txt')
    """
    text = os.path.expanduser(_validated_path_value(path_value, name))
    path = (base_dir or Path.cwd()).joinpath(text)
    resolved = path.resolve(strict=False)
    if allowed_roots is not None and not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"{name} must stay under an authorized root")
    return resolved


def validate_path_component(value: object, name: str = "path component") -> str:
    """Validate an identifier before using it as one filesystem component."""
    text = str(value).strip()
    if not text or len(text) > 128:
        raise ValueError(f"{name} must contain between 1 and 128 characters")
    if text in {".", ".."} or text.endswith("."):
        raise ValueError(f"{name} must be a safe filename component")
    if any(not (char.isalnum() or char in "._-") for char in text):
        raise ValueError(f"{name} may contain only letters, numbers, dots, underscores, and hyphens")
    if PureWindowsPath(text).is_reserved():
        raise ValueError(f"{name} must not be a reserved Windows filename")
    return text


def safe_child_path(parent: Path, filename: str | Path, name: str = "output file") -> Path:
    """Resolve one child path and require it to stay under its canonical parent."""
    parent = parent.resolve(strict=False)
    return resolve_path(filename, parent, allowed_roots=(parent,), name=name)
