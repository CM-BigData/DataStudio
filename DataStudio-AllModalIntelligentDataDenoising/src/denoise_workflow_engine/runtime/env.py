from __future__ import annotations

import os
from pathlib import Path


def load_local_env(base_dir: Path | None = None, override: bool = False) -> dict[str, str]:
    """Load local API environment variables from project files.

    Business logic:
        1. Respect the explicit skip flag before reading local env files.
        2. Search candidate env file locations in order.
        3. Load `KEY=VALUE` pairs into the process environment and return the injected entries.

    Args:
            base_dir (Path | None): Base directory used to resolve candidate files.
            override (bool): Whether to overwrite existing environment variables.

    Returns:
        dict[str, str]: Environment variables loaded during this call.

    Examples:
        >>> callable(load_local_env)
        True
    """
    if os.getenv("DENOISE_SKIP_LOCAL_ENV", "").strip().lower() in {"1", "true", "yes"}:  # Skip local env injection when explicitly requested.
        return {}
    root = base_dir or Path.cwd()
    candidates = [
        root / "config" / "local_api.env",
        root / ".env.local",
    ]
    loaded: dict[str, str] = {}
    for path in candidates:  # Check candidate files in a fixed order.
        if not path.exists():  # Skip missing files.
            continue
        for line in path.read_text(encoding="utf-8").splitlines():  # Read line by line to keep parsing simple and deterministic.
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:  # Ignore blank lines, comments, and invalid env rows.
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if not key:  # Ignore rows without a valid key.
                continue
            if override or key not in os.environ:  # Only inject when override is allowed or the key is absent.
                os.environ[key] = value
                loaded[key] = value
    return loaded
