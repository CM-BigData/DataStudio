from __future__ import annotations

from pathlib import Path

import parse_engine.operators  # noqa: F401
from parse_engine.models import DataItem
from parse_engine.operators.audio_parse.asr.backends.base import AsrResult, AsrSegment
from parse_engine.operators.audio_parse.asr.operator import AudioAsrOperator
from parse_engine.runtime.config import load_workflow_config


class _FakeAsrBackend:
    """Provide a deterministic ASR backend for tests."""

    name = "fake_backend"

    def __init__(self, enabled: bool = True, reason: str = "") -> None:
        self._enabled = enabled
        self._reason = reason

    def is_enabled(self) -> bool:
        """Return whether the fake backend is enabled.

        Business logic:
            1. Expose a stable readiness flag to the operator.
            2. Let tests cover both enabled and disabled branches.
            3. Avoid external dependencies during tests.

        Args:
            None.

        Returns:
            bool: Current enabled state.

        Examples:
            >>> _FakeAsrBackend().is_enabled()
            True
        """
        return self._enabled

    def disabled_reason(self) -> str:
        """Return the configured disabled reason.

        Business logic:
            1. Surface the test-specific disabled reason.
            2. Keep the fake API aligned with real backends.
            3. Return an empty string when enabled.

        Args:
            None.

        Returns:
            str: Disabled reason.

        Examples:
            >>> _FakeAsrBackend(False, "x").disabled_reason()
            'x'
        """
        return self._reason

    def transcribe(self, audio_path: Path) -> AsrResult:
        """Return one deterministic ASR result for the given file.

        Business logic:
            1. Ignore file contents because the test focuses on operator wiring.
            2. Return a normalized ASR result with one segment.
            3. Keep language, confidence, and timing fields populated for assertions.

        Args:
            audio_path (Path): Audio path supplied by the operator.

        Returns:
            AsrResult: Deterministic ASR result.

        Examples:
            >>> _FakeAsrBackend().transcribe(Path("a.wav")).text
            'hello world'
        """
        return AsrResult(
            text="hello world",
            backend=self.name,
            model="fake-model",
            language="en",
            confidence=0.91,
            request_id="req-test",
            latency_ms=12,
            duration_seconds=1.5,
            segments=[AsrSegment(0.0, 1.5, "hello world", 0.91)],
            raw={"source_file": audio_path.name},
        )


def test_audio_workflow_uses_audio_asr_operator() -> None:
    """Verify that the audio workflow keeps ASR config inside step params.

    Business logic:
        1. Load the main audio workflow configuration.
        2. Read the public `audio_parse` step configuration.
        3. Assert that ASR backend settings live under `steps[].params.asr`.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> isinstance("dashscope_qwen_asr", str)
        True
    """
    config = load_workflow_config(Path("workflows/audio_parse.yaml"))
    assert config.steps[0].operator == "audio_parse"
    assert config.steps[0].params["asr"]["provider"] == "dashscope_qwen_asr"
    assert config.steps[0].params["asr"]["enabled"] is True
    assert config.steps[0].params["asr"]["model"] == "qwen3-asr-flash"


def test_audio_asr_operator_prefers_nested_workflow_asr_config() -> None:
    """Verify that workflow `params.asr` is the canonical ASR config source.

    Business logic:
        1. Build an operator with nested `asr` config and conflicting flat keys.
        2. Normalize the configuration through the operator helper.
        3. Assert that nested workflow config wins and no flat fallback leaks in.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> callable(test_audio_asr_operator_prefers_nested_workflow_asr_config)
        True
    """
    operator = AudioAsrOperator(
        {
            "asr": {
                "provider": "dashscope_qwen_asr",
                "enabled": True,
                "model": "nested-model",
            },
            "provider": "faster_whisper",
            "model": "flat-model",
        }
    )

    merged = operator._merged_asr_config()

    assert merged == {
        "provider": "dashscope_qwen_asr",
        "enabled": True,
        "model": "nested-model",
    }


def test_audio_asr_operator_writes_real_transcript_artifact(tmp_path: Path) -> None:
    """Verify that the audio ASR operator writes a real transcript artifact.

    Business logic:
        1. Create a fake audio sample and inject a deterministic backend.
        2. Run the operator on the audio sample.
        3. Assert that transcript artifact, metrics, and intermediate text are populated.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> callable(test_audio_asr_operator_writes_real_transcript_artifact)
        True
    """
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"RIFFdemo")
    item = DataItem.from_path(audio_path)
    operator = AudioAsrOperator({"backend_instance": _FakeAsrBackend()})
    operator.setup()

    processed = operator.process(item)

    assert processed.artifacts
    artifact = processed.artifacts[0]
    assert artifact.type == "asr_text"
    assert artifact.text == "hello world"
    assert artifact.data["backend"] == "fake_backend"
    assert processed.intermediate["asr_text"] == "hello world"
    assert processed.metrics["asr_language"] == "en"
    assert processed.metrics["asr_segment_count"] == 1
    assert processed.action == "parsed"


def test_audio_asr_operator_reports_not_configured_without_placeholder_artifact(tmp_path: Path) -> None:
    """Verify that an unconfigured backend fails explicitly without fake artifacts.

    Business logic:
        1. Create a fake audio sample and inject a disabled backend.
        2. Run the operator on the audio sample.
        3. Assert that no artifact is written and an `asr_not_configured` issue is recorded.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> callable(test_audio_asr_operator_reports_not_configured_without_placeholder_artifact)
        True
    """
    audio_path = tmp_path / "demo.wav"
    audio_path.write_bytes(b"RIFFdemo")
    item = DataItem.from_path(audio_path)
    operator = AudioAsrOperator({"backend_instance": _FakeAsrBackend(False, "backend disabled for test")})
    operator.setup()

    processed = operator.process(item)

    assert not processed.artifacts
    assert processed.metrics["asr_mode"] == "not_configured"
    assert processed.issues[0]["type"] == "asr_not_configured"
