from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import Any, Sequence


def _validated_path_text(value: str | Path, *, name: str) -> str:
    """Validate the textual form of a filesystem path."""
    text = str(value).strip()
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
        text = os.path.expanduser(_validated_path_text(value, name="allow-root"))
        root = Path.cwd().joinpath(text).resolve(strict=True)
        if not root.is_dir():
            raise ValueError("allow-root must be an existing directory")
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def validate_task_id(value: str, *, name: str = "task id") -> str:
    """Validate a task ID before it is used as a filename component."""
    text = str(value).strip()
    if not text:
        raise ValueError(f"{name} must not be empty")
    if len(text) > 128:
        raise ValueError(f"{name} must not exceed 128 characters")
    if text in {".", ".."} or text.endswith("."):
        raise ValueError(f"{name} must be a safe identifier")
    if any(not (char.isalnum() or char in "._-") for char in text):
        raise ValueError(f"{name} may contain only letters, numbers, dots, underscores, and hyphens")
    if PureWindowsPath(text).is_reserved():
        raise ValueError(f"{name} must not be a reserved Windows filename")
    return text


def safe_path(
    value: str | Path,
    *,
    name: str = "path",
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> Path:
    """Validate and resolve a user-provided filesystem path."""
    text = os.path.expanduser(_validated_path_text(value, name=name))
    path = (base_dir or Path.cwd()).joinpath(text)
    resolved = path.resolve(strict=False)
    if allowed_roots is not None and not any(resolved == root or resolved.is_relative_to(root) for root in allowed_roots):
        raise ValueError(f"{name} must stay under an authorized root")
    return resolved


def safe_output_path(
    value: str | Path,
    *,
    name: str = "output path",
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> Path:
    """Validate an output path and reject directory targets."""
    path = safe_path(value, name=name, base_dir=base_dir, allowed_roots=allowed_roots)
    if path.exists() and path.is_dir():
        raise ValueError(f"{name} must be a file path: {path.name}")
    return path


def safe_child_path(parent: Path, value: str | Path, *, name: str = "output file") -> Path:
    """Resolve a configured child path under a known output directory."""
    text = _validated_path_text(value, name=name)
    child = Path().joinpath(text)
    if child.is_absolute() or ".." in child.parts:
        raise ValueError(f"{name} must stay under the output directory")
    return parent / child


def display_path(value: Any, *, cwd: Path | None = None) -> str:
    """Return a command-line-safe path display string."""
    path = Path(str(value))
    try:
        resolved = path.resolve()
        return str(resolved.relative_to((cwd or Path.cwd()).resolve()))
    except (OSError, ValueError):
        return path.name if path.name else "[external-path]"
