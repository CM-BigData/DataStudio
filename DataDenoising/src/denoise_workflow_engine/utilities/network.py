from __future__ import annotations

from urllib.parse import urlsplit


def validate_http_endpoint(value: str, name: str = "API endpoint") -> str:
    """Validate that a remote API endpoint uses HTTP(S) and has a host."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty HTTP(S) URL")
    if value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{name} contains whitespace or control characters")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError(f"{name} is invalid: {exc}") from exc

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"{name} must use http or https")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError(f"{name} must include a host")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{name} contains an invalid port")
    return value
