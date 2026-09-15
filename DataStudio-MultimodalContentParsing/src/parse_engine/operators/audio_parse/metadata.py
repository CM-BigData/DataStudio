from __future__ import annotations

import wave
from pathlib import Path

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class AudioInfoExtractOperator(BaseOperator):
    operator_name = "audio_info_extract"  # Operator name: registry name for the audio metadata extraction step.

    def process(self, item: DataItem) -> DataItem:
        """Extract basic media information from an audio file.

        Business logic:
            1. Pass non-audio samples through unchanged to avoid cross-modality misuse.
            2. For WAV files, prefer the standard-library wave module to read channels, sample rate, and duration.
            3. For other audio formats, probe with soundfile and write results into metrics.

        Args:
            item: Audio or non-audio data item in the current workflow.

        Returns:
            DataItem: Data item with audio metrics written, or the original non-audio item passed through unchanged.

        Examples:
            >>> AudioInfoExtractOperator({}).operator_name
            'audio_info_extract'"""
        if item.modality != "audio":  # Cross-modality guard: the audio probe operator only handles audio samples.
            return item

        path = Path(item.payload["path"])
        if path.suffix.lower() == ".wav":  # WAV fast path: prefer the standard library to read basic audio header information.
            with wave.open(str(path), "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                duration = frames / float(rate) if rate else 0
                item.metrics.update(
                    {
                        "channels": wav.getnchannels(),
                        "sample_rate": rate,
                        "duration_seconds": round(duration, 3),
                        "audio_probe": "wave",
                    }
                )
            return item

        try:
            import soundfile as sf
        except ImportError:
            item.issues.append({"type": "unsupported_audio_probe", "message": "soundfile is required"})
            return item

        info = sf.info(str(path))
        item.metrics.update(
            {
                "channels": info.channels,
                "sample_rate": info.samplerate,
                "duration_seconds": round(float(info.duration), 3),
                "format": info.format,
                "subtype": info.subtype,
                "audio_probe": "soundfile",
            }
        )
        return item
