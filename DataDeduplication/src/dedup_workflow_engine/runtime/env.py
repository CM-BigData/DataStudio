from __future__ import annotations

import os
import re
from pathlib import Path


LOCAL_ENV_FILES = (  # Workflow config: local environment files the command-line attempts to load in order at startup.
    ".env",
    ".env.local",
    "configs/api_env.local",
    "configs/api_env.local.ps1",
)


def load_local_env_files(base_dir: Path | None = None, override: bool = False) -> list[Path]:
    """Load project-supported local environment files.

    Business logic:
        1. Use base_dir or the current directory as the search root.
        2. Load existing files in LOCAL_ENV_FILES order.
        3. Return the list of file paths that were actually loaded.

    Args:
        base_dir (Path | None, optional): Directory used to search for env files. Defaults to the current directory.
        override (bool, optional): Whether to overwrite existing os.environ values. Defaults to False.

    Returns:
        list[Path]: Env files that existed and were loaded successfully.

    Examples:
        >>> isinstance(load_local_env_files(Path(".")), list)
        True
    """
    root = base_dir or Path.cwd()
    loaded: list[Path] = []
    for relative_path in LOCAL_ENV_FILES:  # Preserve precedence by checking files in the declared order.
        path = root / relative_path
        if not path.exists():  # Missing optional env files are expected in clean checkouts.
            continue
        load_env_file(path, override=override)
        loaded.append(path)
    return loaded


def load_env_file(path: Path, override: bool = False) -> None:
    """Load variable assignments from one env file.

    Business logic:
        1. Read UTF-8 text line by line.
        2. Parse POSIX-style or PowerShell-style variable assignments.
        3. Decide whether to write into os.environ based on override.

    Args:
        path (Path): Env file to load.
        override (bool, optional): Whether to overwrite existing environment variables. Defaults to False.

    Returns:
        None: Variables are written into os.environ and nothing is returned.

    Examples:
        >>> load_env_file(Path(".env.missing"), override=False)  # doctest: +SKIP
    """
    for raw_line in path.read_text(encoding="utf-8").splitlines():  # Parse independently so invalid lines do not stop loading.
        parsed = _parse_env_line(raw_line)
        if not parsed:  # Comments, blanks, and malformed lines are ignored.
            continue
        key, value = parsed
        if override or not os.environ.get(key):  # Existing shell values win unless callers opt into replacement.
            os.environ[key] = value


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    """Parse a single environment-variable assignment line.

    Business logic:
        1. Ignore blank lines and comments.
        2. Prefer PowerShell-style $env:NAME = VALUE assignments.
        3. Then recognize POSIX export NAME=VALUE or NAME=VALUE assignments.

    Args:
        raw_line (str): Raw single-line text from an env file.

    Returns:
        tuple[str, str] | None: Parsed key and value, or None when the line cannot be parsed.

    Examples:
        >>> _parse_env_line("export API_KEY='x'")
        ('API_KEY', 'x')
    """
    line = raw_line.strip()
    if not line or line.startswith("#"):  # Empty and comment lines carry no variable assignment.
        return None

    powershell_match = re.match(r"^\$env:([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$", line)
    if powershell_match:  # PowerShell templates use $env:NAME = VALUE syntax.
        return powershell_match.group(1), _unquote_value(powershell_match.group(2))

    if line.startswith("export "):  # POSIX export prefixes should not become part of the key.
        line = line[len("export ") :].strip()
    if "=" not in line:  # Lines without assignment syntax are not env values.
        return None
    key, value = line.split("=", 1)
    key = key.strip()
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key):  # Reject keys that cannot be valid environment names.
        return None
    return key, _unquote_value(value)


def _unquote_value(value: str) -> str:
    """Clean outer quotes and escaped quotes from an env value.

    Business logic:
        1. Strip surrounding whitespace from the value.
        2. Remove paired single or double quotes.
        3. Restore common escaped quote characters.

    Args:
        value (str): Raw variable value from the right side of an equals sign.

    Returns:
        str: Cleaned string suitable for writing into os.environ.

    Examples:
        >>> _unquote_value('"hello"')
        'hello'
    """
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:  # Remove matching shell quotes only.
        value = value[1:-1]
    return value.replace(r"\"", '"').replace(r"\'", "'")
