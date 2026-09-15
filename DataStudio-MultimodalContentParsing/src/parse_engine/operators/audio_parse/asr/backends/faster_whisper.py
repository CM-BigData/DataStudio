from __future__ import annotations

import time
from pathlib import Path

from parse_engine.operators.audio_parse.asr.backends.base import AsrBackendConfig, AsrBackendError, AsrResult, AsrSegment


class FasterWhisperAsrBackend:
    """Represent a local faster-whisper backend."""

    name = "faster_whisper"

    def __init__(self, config: AsrBackendConfig) -> None:
        self.config = config
        self._reason = self._validate_config()
        self._model = None

    def is_enabled(self) -> bool:
        """Return whether the local backend is ready for use.

        Business logic:
            1. Reuse the validation result computed at initialization time.
            2. Avoid lazy model loading when the configuration is already invalid.
            3. Expose a simple readiness flag to the operator.

        Args:
            None.

        Returns:
            bool: True when the backend is ready to load the model.

        Examples:
            >>> FasterWhisperAsrBackend(AsrBackendConfig(provider="faster_whisper", enabled=False)).is_enabled()
            False
        """
        return self._reason is None

    def disabled_reason(self) -> str:
        """Return the current disabled reason if any.

        Business logic:
            1. Expose the validation failure reason directly.
            2. Keep the API aligned with other backends.
            3. Return an empty string when enabled.

        Args:
            None.

        Returns:
            str: Disabled reason or empty string.

        Examples:
            >>> FasterWhisperAsrBackend(AsrBackendConfig(provider="faster_whisper", enabled=False)).disabled_reason()
            'ASR backend is disabled in config'
        """
        return self._reason or ""

    def transcribe(self, audio_path: Path) -> AsrResult:
        """Transcribe one audio file with a local faster-whisper model.

        Business logic:
            1. Validate backend readiness and load the model lazily.
            2. Run local transcription over the audio file.
            3. Normalize segments, language, and confidence into AsrResult.

        Args:
            audio_path (Path): Input audio path.

        Returns:
            AsrResult: Normalized transcription result.

        Examples:
            >>> callable(FasterWhisperAsrBackend.transcribe)
            True
        """
        if not self.is_enabled():
            raise AsrBackendError(self.disabled_reason())
        if not audio_path.exists():
            raise AsrBackendError(f"Audio file does not exist: {audio_path}")
        model = self._load_model()
        start = time.monotonic()
        try:
            segments_iter, info = model.transcribe(
                str(audio_path),
                language=self.config.language,
                initial_prompt=self.config.prompt,
                **self.config.extra,
            )
            segments = [
                AsrSegment(
                    start_seconds=float(segment.start),
                    end_seconds=float(segment.end),
                    text=str(segment.text or ""),
                    confidence=float(segment.avg_logprob + 1.0) if getattr(segment, "avg_logprob", None) is not None else None,
                )
                for segment in segments_iter
            ]
        except Exception as exc:
            raise AsrBackendError(f"faster-whisper ASR failed: {exc}") from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        text = "".join(segment.text for segment in segments).strip()
        confidences = [segment.confidence for segment in segments if segment.confidence is not None]
        return AsrResult(
            text=text,
            backend=self.name,
            model=self.config.model,
            language=getattr(info, "language", self.config.language),
            confidence=round(sum(confidences) / len(confidences), 6) if confidences else None,
            latency_ms=latency_ms,
            duration_seconds=getattr(info, "duration", None),
            segments=segments,
            raw={"language_probability": getattr(info, "language_probability", None)},
        )

    def _load_model(self):
        """Load the local faster-whisper model lazily.

        Business logic:
            1. Reuse the cached model instance when already loaded.
            2. Import the dependency only when the backend is actually used.
            3. Construct the model from the configured model name or path.

        Args:
            None.

        Returns:
            object: Loaded WhisperModel instance.

        Examples:
            >>> callable(FasterWhisperAsrBackend._load_model)
            True
        """
        if self._model is not None:
            return self._model
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AsrBackendError("faster-whisper is required for the local ASR backend") from exc
        self._model = WhisperModel(self.config.model, **self.config.extra)
        return self._model

    def _validate_config(self) -> str | None:
        """Validate local backend configuration before model loading.

        Business logic:
            1. Reject disabled configurations early.
            2. Require the expected provider name.
            3. Require a model name or local path so the local model can be loaded.

        Args:
            None.

        Returns:
            str | None: Disabled reason or None when valid.

        Examples:
            >>> FasterWhisperAsrBackend(AsrBackendConfig(provider="faster_whisper", enabled=False))._validate_config()
            'ASR backend is disabled in config'
        """
        if not self.config.enabled:
            return "ASR backend is disabled in config"
        if self.config.provider != self.name:
            return f"ASR provider mismatch: expected {self.name}, got {self.config.provider or 'empty'}"
        if not self.config.model:
            return "Local ASR model path is required"
        return None
