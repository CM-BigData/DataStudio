from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


class AsrBackendError(RuntimeError):
    """Represent an error raised by the ASR backend layer."""


@dataclass
class AsrSegment:
    """Represent one ASR transcript segment."""

    start_seconds: float
    end_seconds: float
    text: str
    confidence: float | None = None


@dataclass
class AsrResult:
    """Represent one normalized ASR transcription result."""

    text: str
    backend: str
    model: str
    language: str | None = None
    confidence: float | None = None
    request_id: str | None = None
    latency_ms: int = 0
    duration_seconds: float | None = None
    segments: list[AsrSegment] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class AsrBackendConfig:
    """Represent normalized backend configuration for ASR adapters."""

    provider: str
    enabled: bool
    model: str = ""
    api_base: str | None = None
    api_key: str | None = None
    timeout_seconds: int = 60
    language: str | None = None
    prompt: str | None = None
    temperature: float | None = None
    response_format: str = "verbose_json"
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AsrBackendConfig":
        """Create backend config from operator or registry config.

        Business logic:
            1. Read explicit provider and enabled flags first.
            2. Resolve direct values or environment-backed values for secrets and endpoints.
            3. Preserve unknown fields in `extra` so backend-specific settings remain extensible.

        Args:
            raw (dict[str, Any]): Raw backend configuration.

        Returns:
            AsrBackendConfig: Normalized backend configuration.

        Examples:
            >>> AsrBackendConfig.from_dict({"provider": "openai_compatible", "enabled": True}).provider
            'openai_compatible'
        """
        provider = str(raw.get("provider", "") or "").strip().lower()
        enabled = bool(raw.get("enabled", False))
        known_keys = {
            "provider",
            "enabled",
            "model",
            "api_base",
            "api_base_env",
            "api_key",
            "api_key_env",
            "timeout_seconds",
            "language",
            "prompt",
            "temperature",
            "response_format",
        }
        return cls(
            provider=provider,
            enabled=enabled,
            model=str(raw.get("model", "") or "").strip(),
            api_base=_read_config_or_env(raw, "api_base", "api_base_env"),
            api_key=_read_config_or_env(raw, "api_key", "api_key_env"),
            timeout_seconds=int(raw.get("timeout_seconds", 60)),
            language=str(raw["language"]) if raw.get("language") else None,
            prompt=str(raw["prompt"]) if raw.get("prompt") else None,
            temperature=float(raw["temperature"]) if raw.get("temperature") is not None else None,
            response_format=str(raw.get("response_format", "verbose_json")),
            extra={key: value for key, value in raw.items() if key not in known_keys},
        )


class AsrBackend(Protocol):
    """Describe the stable backend interface used by the ASR operator."""

    name: str

    def is_enabled(self) -> bool:
        """Return whether the backend is ready for real transcription."""

    def disabled_reason(self) -> str:
        """Return a human-readable reason when the backend is disabled."""

    def transcribe(self, audio_path: Path) -> AsrResult:
        """Transcribe one audio file and return a normalized result."""


class DisabledAsrBackend:
    """Represent a non-runnable backend that reports a configuration reason."""

    def __init__(self, reason: str, name: str = "disabled") -> None:
        self.name = name
        self._reason = reason

    def is_enabled(self) -> bool:
        """Return False because this backend is intentionally disabled.

        Business logic:
            1. Expose a stable readiness API to the operator.
            2. Make the disabled state explicit instead of pretending success.
            3. Let the operator surface the reason through metrics and issues.

        Args:
            None.

        Returns:
            bool: Always False.

        Examples:
            >>> DisabledAsrBackend("x").is_enabled()
            False
        """
        return False

    def disabled_reason(self) -> str:
        """Return the reason why the backend is unavailable.

        Business logic:
            1. Return the stored disabled reason verbatim.
            2. Avoid hiding configuration problems.
            3. Give the operator an explainable metric value.

        Args:
            None.

        Returns:
            str: Disabled reason.

        Examples:
            >>> DisabledAsrBackend("missing").disabled_reason()
            'missing'
        """
        return self._reason

    def transcribe(self, audio_path: Path) -> AsrResult:
        """Reject transcription attempts for disabled backends.

        Business logic:
            1. Refuse to transcribe when the backend is not enabled.
            2. Raise a clear backend error instead of returning fake output.
            3. Include the disabled reason in the exception message.

        Args:
            audio_path (Path): Audio path requested for transcription.

        Returns:
            AsrResult: This method never returns.

        Examples:
            >>> callable(DisabledAsrBackend("x").transcribe)
            True
        """
        raise AsrBackendError(f"ASR backend is disabled: {self._reason}")


def _read_config_or_env(raw: dict[str, Any], value_key: str, env_key: str) -> str | None:
    """Read a direct config value or an environment-backed value.

    Business logic:
        1. Prefer a direct configured value when present.
        2. Otherwise read the environment variable named by the config.
        3. Return None when neither source exists.

    Args:
        raw (dict[str, Any]): Raw configuration.
        value_key (str): Direct-value field name.
        env_key (str): Environment-variable-name field name.

    Returns:
        str | None: Resolved config value or None.

    Examples:
        >>> _read_config_or_env({"api_key": "x"}, "api_key", "api_key_env")
        'x'
    """
    if raw.get(value_key):
        return str(raw[value_key])
    if raw.get(env_key):
        env_name = str(raw[env_key])
        value = os.getenv(env_name)
        if value is None:
            raise AsrBackendError(f"Required environment variable is missing: {env_name}")
        return value
    return None
