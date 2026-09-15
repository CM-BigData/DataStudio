from __future__ import annotations

from parse_engine.operators.audio_parse.asr.backends.base import AsrBackend, AsrBackendConfig, DisabledAsrBackend
from parse_engine.operators.audio_parse.asr.backends.dashscope_qwen import DashScopeQwenAsrBackend
from parse_engine.operators.audio_parse.asr.backends.faster_whisper import FasterWhisperAsrBackend
from parse_engine.operators.audio_parse.asr.backends.openai_compatible import OpenAICompatibleAsrBackend


def build_asr_backend(raw_config: dict) -> AsrBackend:
    """Build one ASR backend from raw operator or registry config.

    Business logic:
        1. Normalize raw config through AsrBackendConfig.
        2. Select the concrete backend by provider name.
        3. Return a disabled backend when the config is unsupported or intentionally disabled.

    Args:
        raw_config (dict): Raw ASR configuration.

    Returns:
        AsrBackend: Concrete or disabled backend instance.

    Examples:
        >>> build_asr_backend({"provider": "unknown", "enabled": True}).is_enabled()
        False
    """
    try:
        config = AsrBackendConfig.from_dict(raw_config or {})
    except Exception as exc:
        return DisabledAsrBackend(str(exc), name="invalid_config")
    if not config.enabled:
        return DisabledAsrBackend("ASR backend is disabled in config")
    if config.provider == "openai_compatible":
        return OpenAICompatibleAsrBackend(config)
    if config.provider == "dashscope_qwen_asr":
        return DashScopeQwenAsrBackend(config)
    if config.provider == "faster_whisper":
        return FasterWhisperAsrBackend(config)
    return DisabledAsrBackend(f"Unsupported ASR provider: {config.provider or 'empty'}", name="unsupported")
