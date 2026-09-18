from __future__ import annotations

import base64
import mimetypes
import time
from pathlib import Path
from typing import Any

from parse_engine.operators.audio_parse.asr.backends.base import AsrBackendConfig, AsrBackendError, AsrResult, AsrSegment


class DashScopeQwenAsrBackend:
    """Represent a DashScope Qwen chat-completions ASR backend."""

    name = "dashscope_qwen_asr"
    default_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    def __init__(self, config: AsrBackendConfig) -> None:
        self.config = config
        self._reason = self._validate_config()

    def is_enabled(self) -> bool:
        """Return whether the backend is fully configured for file transcription.

        Business logic:
            1. Reuse the validation result computed at initialization time.
            2. Avoid outbound requests when required fields are missing.
            3. Expose a stable readiness API to the operator.

        Args:
            None.

        Returns:
            bool: True when the backend can transcribe audio files.

        Examples:
            >>> DashScopeQwenAsrBackend(AsrBackendConfig(provider="dashscope_qwen_asr", enabled=False)).is_enabled()
            False
        """
        return self._reason is None

    def disabled_reason(self) -> str:
        """Return the disabled reason or an empty string.

        Business logic:
            1. Surface the current validation failure directly.
            2. Keep the API aligned with other ASR backends.
            3. Return an empty string when the backend is ready.

        Args:
            None.

        Returns:
            str: Disabled reason when present.

        Examples:
            >>> DashScopeQwenAsrBackend(AsrBackendConfig(provider="dashscope_qwen_asr", enabled=False)).disabled_reason()
            'ASR backend is disabled in config'
        """
        return self._reason or ""

    def transcribe(self, audio_path: Path) -> AsrResult:
        """Transcribe one local audio file through DashScope Qwen ASR.

        Business logic:
            1. Validate backend readiness and input file existence.
            2. Encode the local audio file as base64 and send it through `chat.completions`.
            3. Normalize the model output into the shared AsrResult structure.

        Args:
            audio_path (Path): Input audio path.

        Returns:
            AsrResult: Normalized transcription result.

        Examples:
            >>> callable(DashScopeQwenAsrBackend.transcribe)
            True
        """
        if not self.is_enabled():
            raise AsrBackendError(self.disabled_reason())
        if not audio_path.exists():
            raise AsrBackendError(f"Audio file does not exist: {audio_path}")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise AsrBackendError("openai is required for the DashScope Qwen ASR backend") from exc

        client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.api_base or self.default_base_url,
        )
        start = time.monotonic()
        try:
            response = client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {
                                    "data": _build_audio_data_url(audio_path),
                                    "format": _detect_audio_format(audio_path),
                                },
                            }
                        ],
                    }
                ],
                extra_body={
                    "asr_options": {
                        "language_hints": [self.config.language] if self.config.language else [],
                    }
                },
                timeout=self.config.timeout_seconds,
                **self.config.extra,
            )
        except Exception as exc:
            raise AsrBackendError(f"DashScope Qwen ASR failed: {exc}") from exc

        payload = _response_to_dict(response)
        text = _extract_text_from_chat_payload(payload)
        segments = [AsrSegment(start_seconds=0.0, end_seconds=0.0, text=text, confidence=None)] if text else []
        return AsrResult(
            text=text,
            backend=self.name,
            model=str(payload.get("model", self.config.model) or self.config.model),
            language=self.config.language,
            confidence=_average_confidence(segments),
            request_id=_extract_request_id(response, payload),
            latency_ms=int((time.monotonic() - start) * 1000),
            duration_seconds=None,
            segments=segments,
            raw=payload,
        )

    def _validate_config(self) -> str | None:
        """Validate backend configuration before runtime calls.

        Business logic:
            1. Reject disabled configurations early.
            2. Require the expected provider name and model id.
            3. Require an API key because the backend is remote.

        Args:
            None.

        Returns:
            str | None: Disabled reason or None when valid.

        Examples:
            >>> DashScopeQwenAsrBackend(AsrBackendConfig(provider="dashscope_qwen_asr", enabled=False))._validate_config()
            'ASR backend is disabled in config'
        """
        if not self.config.enabled:
            return "ASR backend is disabled in config"
        if self.config.provider != self.name:
            return f"ASR provider mismatch: expected {self.name}, got {self.config.provider or 'empty'}"
        if not self.config.model:
            return "DashScope Qwen ASR model is required"
        if not self.config.api_key:
            return "ASR api_key or api_key_env is required"
        return None


def _response_to_dict(response: Any) -> dict[str, Any]:
    """Normalize an SDK response object into a dictionary.

    Business logic:
        1. Prefer `model_dump()` when the SDK exposes it.
        2. Support dict-like responses directly.
        3. Fall back to the small set of fields used by the parser.

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


def _build_audio_data_url(audio_path: Path) -> str:
    """Convert a local audio file into the base64 payload required by DashScope Qwen.

    Business logic:
        1. Detect the MIME type from the local file suffix.
        2. Base64-encode the audio bytes.
        3. Build a `data:` URL string for `input_audio.data`.

    Args:
        audio_path (Path): Local audio file path.

    Returns:
        str: Data URL string containing the base64 audio payload.

    Examples:
        >>> _build_audio_data_url(Path(__file__)).startswith("data:")
        True
    """
    mime_type = mimetypes.guess_type(audio_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(audio_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _detect_audio_format(audio_path: Path) -> str:
    """Detect the audio format label expected by the DashScope request body.

    Business logic:
        1. Read the file suffix and normalize it to lowercase.
        2. Drop the leading dot so the API receives a plain format label.
        3. Fall back to `wav` when the suffix is missing.

    Args:
        audio_path (Path): Local audio file path.

    Returns:
        str: Format label such as `flac` or `wav`.

    Examples:
        >>> _detect_audio_format(Path("demo.flac"))
        'flac'
    """
    suffix = audio_path.suffix.lower().lstrip(".")
    return suffix or "wav"


def _extract_text_from_chat_payload(payload: dict[str, Any]) -> str:
    """Extract transcript text from a chat-completions payload.

    Business logic:
        1. Traverse the first choice message returned by the model.
        2. Support either plain string content or structured content blocks.
        3. Return the joined text so the parser gets one stable transcript string.

    Args:
        payload (dict[str, Any]): Normalized response payload.

    Returns:
        str: Extracted transcript text.

    Examples:
        >>> _extract_text_from_chat_payload({"choices": [{"message": {"content": "x"}}]})
        'x'
    """
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()
    return ""


def _extract_request_id(response: Any, payload: dict[str, Any]) -> str | None:
    """Extract a request id from SDK response metadata when available.

    Business logic:
        1. Prefer explicit payload request identifiers first.
        2. Fall back to response object attributes or dict values.
        3. Return None when the SDK does not expose any request id.

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
        2. Fall back to average log probability when provided.
        3. Return None when no confidence-like field exists.

    Args:
        segment (dict[str, Any]): Segment payload.

    Returns:
        float | None: Confidence-like value when available.

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
        2. Compute the arithmetic mean for the remaining segments.
        3. Return None when no segment exposes confidence-like data.

    Args:
        segments (list[AsrSegment]): Segment list.

    Returns:
        float | None: Average confidence or None.

    Examples:
        >>> _average_confidence([AsrSegment(0, 1, "x", 0.8), AsrSegment(1, 2, "y", 0.6)])
        0.7
    """
    values = [segment.confidence for segment in segments if segment.confidence is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 6)
