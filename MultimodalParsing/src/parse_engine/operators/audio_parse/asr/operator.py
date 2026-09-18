from __future__ import annotations

from pathlib import Path
from typing import Any

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.audio_parse.asr import build_asr_backend
from parse_engine.operators.audio_parse.asr.backends.base import AsrBackendError, AsrResult
from parse_engine.operators.base import BaseOperator


class AudioAsrOperator(BaseOperator):
    operator_name = "audio_asr"  # Operator name: registry name for the audio transcription step.

    def setup(self) -> None:
        """Initialize the configured ASR backend.

        Business logic:
            1. Prefer a test-injected backend instance when present.
            2. Otherwise normalize step-level ASR config from the workflow.
            3. Build one concrete backend through the shared ASR factory.

        Args:
            None.

        Returns:
            None: The backend instance is stored on the operator.

        Examples:
            >>> AudioAsrOperator({"backend_instance": object()}).config["backend_instance"].__class__ is object
            True
        """
        injected = self.config.get("backend_instance")
        if injected is not None and hasattr(injected, "transcribe") and hasattr(injected, "is_enabled"):
            self.backend = injected
            return
        self.backend = build_asr_backend(self._merged_asr_config())

    def process(self, item: DataItem) -> DataItem:
        """Run ASR on an audio sample and write a stable transcript artifact.

        Business logic:
            1. Pass non-audio samples through unchanged.
            2. Fail clearly when the backend is not configured instead of writing a fake placeholder transcript.
            3. On success, append a real ASR artifact and store searchable metrics and intermediate text.

        Args:
            item: Audio or non-audio data item in the current workflow.

        Returns:
            DataItem: Data item updated with ASR results or failure issues.

        Examples:
            >>> AudioAsrOperator({}).operator_name
            'audio_asr'"""
        if item.modality != "audio":  # Cross-modality guard: the ASR placeholder artifact is only attached to audio samples.
            return item

        path = Path(item.payload["path"])
        if not getattr(self, "backend", None) or not self.backend.is_enabled():
            reason = getattr(self.backend, "disabled_reason", lambda: "ASR backend is not configured")()
            item.metrics["asr_mode"] = "not_configured"
            item.metrics["asr_backend"] = getattr(self.backend, "name", "disabled")
            item.issues.append({"type": "asr_not_configured", "message": reason})
            return item

        try:
            result = self.backend.transcribe(path)
        except AsrBackendError as exc:
            item.metrics["asr_mode"] = "error"
            item.metrics["asr_backend"] = getattr(self.backend, "name", "unknown")
            item.issues.append({"type": "asr_error", "message": str(exc)})
            return item

        item.artifacts.append(
            Artifact(
                id=f"{item.id}_asr",
                type="asr_text",
                text=result.text,
                data=self._artifact_data(result),
                source_trace=SourceTrace(file=str(path), operator=self.operator_name),
            )
        )
        item.intermediate["asr_text"] = result.text
        item.metrics["asr_mode"] = "backend"
        item.metrics["asr_backend"] = result.backend
        item.metrics["asr_model"] = result.model
        item.metrics["asr_language"] = result.language
        item.metrics["asr_confidence"] = result.confidence
        item.metrics["asr_segment_count"] = len(result.segments)
        item.metrics["asr_latency_ms"] = result.latency_ms
        item.metrics["asr_text_length"] = len(result.text.strip())
        if not result.text.strip():  # Empty transcripts are preserved as real backend output but still flagged for review.
            item.issues.append({"type": "asr_empty_text", "message": "ASR returned an empty transcript"})
        item.action = "parsed"
        return item

    def _merged_asr_config(self) -> dict[str, Any]:
        """规范化 workflow 中声明的 ASR 配置

        Business logic:
            1. 优先读取 `config.asr` 作为 workflow 显式声明的 ASR 配置。
            2. 兼容旧的扁平 step 参数写法，便于测试和过渡。
            3. 返回可直接交给 backend factory 的统一配置字典。

        Args:
            None.

        Returns:
            dict[str, Any]: Normalized backend configuration.

        Examples:
            >>> isinstance(AudioAsrOperator({})._merged_asr_config(), dict)
            True
        """
        step_config = self.config.get("asr")
        if isinstance(step_config, dict):
            return dict(step_config)

        merged: dict[str, Any] = {}
        for key in [
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
            "compute_type",
            "device",
            "beam_size",
        ]:
            if key in self.config:
                merged[key] = self.config[key]
        return merged

    def _artifact_data(self, result: AsrResult) -> dict[str, Any]:
        """Convert an ASR result into artifact metadata.

        Business logic:
            1. Copy stable backend, model, timing, and language fields.
            2. Serialize segments into plain dictionaries for JSON output.
            3. Preserve the raw backend payload for replay or debugging.

        Args:
            result (AsrResult): Normalized ASR result.

        Returns:
            dict[str, Any]: Artifact metadata dictionary.

        Examples:
            >>> AudioAsrOperator({})._artifact_data(AsrResult(text="x", backend="b", model="m"))["backend"]
            'b'
        """
        return {
            "backend": result.backend,
            "model": result.model,
            "language": result.language,
            "confidence": result.confidence,
            "request_id": result.request_id,
            "latency_ms": result.latency_ms,
            "duration_seconds": result.duration_seconds,
            "segments": [
                {
                    "start_seconds": segment.start_seconds,
                    "end_seconds": segment.end_seconds,
                    "text": segment.text,
                    "confidence": segment.confidence,
                }
                for segment in result.segments
            ],
            "raw": result.raw,
        }
