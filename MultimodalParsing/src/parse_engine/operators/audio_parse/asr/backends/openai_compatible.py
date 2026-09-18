from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from parse_engine.operators.audio_parse.asr.backends.base import AsrBackendConfig, AsrBackendError, AsrResult, AsrSegment


class OpenAICompatibleAsrBackend:
    """Represent an OpenAI-compatible audio transcription backend."""

    name = "openai_compatible"

    def __init__(self, config: AsrBackendConfig) -> None:
        self.config = config
        self._reason = self._validate_config()

    def is_enabled(self) -> bool:
        """Return whether the backend is fully configured for real use.

        Business logic:
            1. Check whether validation produced any disabled reason.
            2. Avoid provider calls when required config is missing.
            3. Expose a simple boolean used by the operator.

        Args:
            None.

        Returns:
            bool: True when the backend can transcribe.

        Examples:
            >>> OpenAICompatibleAsrBackend(AsrBackendConfig(provider="openai_compatible", enabled=False)).is_enabled()
            False
        """
        return self._reason is None

    def disabled_reason(self) -> str:
        """Return the disabled reason or a generic empty string.

        Business logic:
            1. Expose the current validation failure reason when unavailable.
            2. Keep the API stable for the operator.
            3. Return an empty string when no problem exists.

        Args:
            None.

        Returns:
            str: Disabled reason when present.

        Examples:
            >>> OpenAICompatibleAsrBackend(AsrBackendConfig(provider="openai_compatible", enabled=False)).disabled_reason()
            'ASR backend is disabled in config'
        """
        return self._reason or ""

    def transcribe(self, audio_path: Path) -> AsrResult:
        """Transcribe one audio file through an OpenAI-compatible API.

        Business logic:
            1. Validate that the backend is enabled and the audio file exists.
            2. Call the OpenAI-compatible transcription endpoint with the configured parameters.
            3. Normalize the response into a stable AsrResult structure.

        Args:
            audio_path (Path): Input audio path.

        Returns:
            AsrResult: Normalized transcription result.

        Examples:
            >>> callable(OpenAICompatibleAsrBackend.transcribe)
            True
        """
        if not self.is_enabled():
            raise AsrBackendError(self.disabled_reason())
        if not audio_path.exists():
            raise AsrBackendError(f"Audio file does not exist: {audio_path}")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AsrBackendError("openai is required for the OpenAI-compatible ASR backend") from exc

        client_kwargs: dict[str, Any] = {}
        if self.config.api_base:
            client_kwargs["base_url"] = self.config.api_base
        if self.config.api_key:
            client_kwargs["api_key"] = self.config.api_key
        start = time.monotonic()
        try:
            client = OpenAI(**client_kwargs)
            with audio_path.open("rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model=self.config.model,
                    file=audio_file,
                    language=self.config.language,
                    prompt=self.config.prompt,
                    temperature=self.config.temperature,
                    response_format=self.config.response_format,
                    timeout=self.config.timeout_seconds,
                    **self.config.extra,
                )
        except Exception as exc:
            raise AsrBackendError(f"OpenAI-compatible ASR failed: {exc}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        payload = _response_to_dict(response)
        segments = [
            AsrSegment(
                start_seconds=float(segment.get("start", 0.0)),
                end_seconds=float(segment.get("end", 0.0)),
                text=str(segment.get("text", "") or ""),
                confidence=_segment_confidence(segment),
            )
            for segment in payload.get("segments", []) or []
        ]
        return AsrResult(
            text=str(payload.get("text", "") or ""),
            backend=self.name,
            model=str(payload.get("model", self.config.model) or self.config.model),
            language=str(payload["language"]) if payload.get("language") else self.config.language,
            confidence=_average_confidence(segments),
            request_id=_extract_request_id(response, payload),
            latency_ms=latency_ms,
            duration_seconds=float(payload["duration"]) if payload.get("duration") is not None else None,
            segments=segments,
            raw=payload,
        )

    def _validate_config(self) -> str | None:
        """Validate backend configuration before runtime calls.

        Business logic:
            1. Reject disabled configurations early.
            2. Require a model name for transcription requests.
            3. Require an API key because the backend is remote.

        Args:
            None.

        Returns:
            str | None: Disabled reason or None when valid.

        Examples:
            >>> OpenAICompatibleAsrBackend(AsrBackendConfig(provider="openai_compatible", enabled=False))._validate_config()
            'ASR backend is disabled in config'
        """
        if not self.config.enabled:
            return "ASR backend is disabled in config"
        if self.config.provider != self.name:
            return f"ASR provider mismatch: expected {self.name}, got {self.config.provider or 'empty'}"
        if not self.config.model:
            return "ASR model is required"
        if not self.config.api_key:
            return "ASR api_key or api_key_env is required"
        return None


def _response_to_dict(response: Any) -> dict[str, Any]:
    """Normalize an SDK response object into a dictionary.

    Business logic:
        1. Prefer a built-in dump method when available.
        2. Support dict-like responses directly.
        3. Fall back to selected attributes for compatibility across SDK variants.

    Args:
        response (Any): SDK response object.

    Returns:
        dict[str, Any]: Dictionary view of the response.

    Examples:
        >>> _response_to_dict({"text": "x"})["text"]
        'x'
    """
    if hasattr(response, "model_dump"):
        return dict(response.model_dump())
    if isinstance(response, dict):
        return dict(response)
    return {
        "text": getattr(response, "text", ""),
        "language": getattr(response, "language", None),
        "duration": getattr(response, "duration", None),
        "segments": getattr(response, "segments", None),
        "model": getattr(response, "model", None),
    }


def _extract_request_id(response: Any, payload: dict[str, Any]) -> str | None:
    """Extract a request id from SDK response metadata when available.

    Business logic:
        1. Prefer explicit payload request-id fields.
        2. Fall back to response object attributes.
        3. Return None when no request id is exposed.

    Args:
        response (Any): SDK response object.
        payload (dict[str, Any]): Normalized response payload.

    Returns:
        str | None: Request id when available.

    Examples:
        >>> _extract_request_id({"id": "x"}, {"id": "x"})
        'x'
    """
    for key in ["request_id", "id"]:
        if payload.get(key):
            return str(payload[key])
        if isinstance(response, dict) and response.get(key):
            return str(response[key])
        if getattr(response, key, None):
            return str(getattr(response, key))
    return None


def _segment_confidence(segment: dict[str, Any]) -> float | None:
    """Extract a confidence-like value from one segment.

    Business logic:
        1. Prefer explicit confidence values when present.
        2. Fall back to average log probability when provided by the backend.
        3. Return None when the backend does not expose confidence-like fields.

    Args:
        segment (dict[str, Any]): Segment payload.

    Returns:
        float | None: Confidence-like value in the range [0, 1] when possible.

    Examples:
        >>> _segment_confidence({"confidence": 0.8})
        0.8
    """
    if segment.get("confidence") is not None:
        return max(0.0, min(1.0, float(segment["confidence"])))
    if segment.get("avg_logprob") is not None:
        value = float(segment["avg_logprob"])
        return max(0.0, min(1.0, 1.0 + value))
    return None


def _average_confidence(segments: list[AsrSegment]) -> float | None:
    """Average segment confidences into one sample-level value.

    Business logic:
        1. Ignore segments without confidence values.
        2. Compute the arithmetic mean for remaining segments.
        3. Return None when no confidence-like values exist.

    Args:
        segments (list[AsrSegment]): Segment list.

    Returns:
        float | None: Average confidence or None.

    Examples:
        >>> _average_confidence([AsrSegment(0, 1, "x", 0.5), AsrSegment(1, 2, "y", 1.0)])
        0.75
    """
    values = [segment.confidence for segment in segments if segment.confidence is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 6)
