from __future__ import annotations

import hashlib
import math
import wave
from pathlib import Path
from typing import Any

from quality_eval.operators.common.base import BaseOperator

try:
    import audioop
except ModuleNotFoundError:  # Python 3.13 removed audioop; pure-Python PCM helpers below cover the needed metrics.
    audioop = None


class AudioDecodeEvalOperator(BaseOperator):
    operator_name: str = "audio_decode_eval"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        audio_path = item.get("payload", {}).get("audio_path")
        if not audio_path:
            self.add_issue(item, "missing_audio_path")
            self.metric(item, "audio_readable", False)
            return item

        path = Path(str(audio_path))
        if not path.exists():
            self.add_issue(item, "audio_not_found")
            self.metric(item, "audio_readable", False)
            return item

        item.setdefault("intermediate", {})["audio_path_abs"] = str(path)
        item["intermediate"]["audio_file_suffix"] = path.suffix.lower().lstrip(".")
        self.metric(item, "audio_file_size", path.stat().st_size)
        self.metric(item, "audio_file_suffix", item["intermediate"]["audio_file_suffix"])
        try:
            item["intermediate"]["audio_file_hash"] = _file_sha256(path)
        except Exception:
            self.add_issue(item, "audio_hash_failed")

        if path.suffix.lower() != ".wav":
            self.metric(item, "audio_readable", False)
            self.metric(item, "audio_decode_reason", "unsupported_decoder")
            return item

        try:
            with wave.open(str(path), "rb") as wav:
                frames = wav.getnframes()
                rate = wav.getframerate()
                channels = wav.getnchannels()
                sample_width = wav.getsampwidth()
                raw = wav.readframes(frames)
            bit_depth = sample_width * 8
            duration = round(frames / rate, 4) if rate else 0
            item["intermediate"].update(
                {
                    "audio_sample_rate": rate,
                    "audio_channels": channels,
                    "audio_sample_width": sample_width,
                    "audio_bit_depth": bit_depth,
                    "audio_duration_seconds": duration,
                    "audio_pcm_hash": _pcm_sha256(channels, sample_width, rate, raw),
                    "audio_rms": _pcm_rms(raw, sample_width) if raw else 0,
                    "audio_minmax": _pcm_minmax(raw, sample_width) if raw else (0, 0),
                    "audio_clip_ratio": _clip_ratio(raw, sample_width, channels),
                    "audio_noise_echo_metrics": _noise_echo_metrics(raw, sample_width, channels, rate),
                }
            )
            self.metric(item, "audio_readable", True)
            self.metric(item, "audio_sample_rate", rate)
            self.metric(item, "audio_channels", channels)
            self.metric(item, "audio_bit_depth", bit_depth)
            self.metric(item, "audio_duration_seconds", duration)
        except Exception as exc:
            self.add_issue(item, "audio_decode_failed")
            self.metric(item, "audio_readable", False)
            self.metric(item, "audio_decode_reason", str(exc))
        return item


class AudioFormatEvalOperator(BaseOperator):
    operator_name: str = "audio_format_eval"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        expected = {str(value).lower().lstrip(".") for value in self.rules.get("allowed_audio_formats", ["wav"])}
        actual = str(item.get("intermediate", {}).get("audio_file_suffix", "")).lower()
        ok = bool(actual) and actual in expected
        self.metric(item, "audio_format_ok", ok)
        if not ok:
            self.add_issue(item, "unsupported_audio_format")
        return item


class AudioSampleRateEvalOperator(BaseOperator):
    operator_name: str = "audio_sample_rate_eval"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        expected = int(self.rules.get("expected_sample_rate", 24000))
        actual = item.get("intermediate", {}).get("audio_sample_rate")
        ok = actual == expected
        self.metric(item, "audio_sample_rate_ok", ok)
        if not ok:
            self.add_issue(item, "audio_sample_rate_mismatch")
        return item


class AudioBitDepthEvalOperator(BaseOperator):
    operator_name: str = "audio_bit_depth_eval"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        expected = int(self.rules.get("expected_bit_depth", 16))
        actual = item.get("intermediate", {}).get("audio_bit_depth")
        ok = actual == expected
        self.metric(item, "audio_bit_depth_ok", ok)
        if not ok:
            self.add_issue(item, "audio_bit_depth_mismatch")
        return item


class AudioVolumeRangeEvalOperator(BaseOperator):
    operator_name: str = "audio_volume_range_eval"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        rms = int(item.get("intermediate", {}).get("audio_rms") or 0)
        low, high = item.get("intermediate", {}).get("audio_minmax") or (0, 0)
        dynamic_range = int(high - low)
        min_rms = int(self.rules.get("min_audio_rms", 100))
        min_dynamic_range = int(self.rules.get("min_audio_dynamic_range", 500))
        ok = rms >= min_rms and dynamic_range >= min_dynamic_range
        self.metric(item, "audio_rms", rms)
        self.metric(item, "audio_dynamic_range", dynamic_range)
        self.metric(item, "audio_volume_range_ok", ok)
        if not ok:
            self.add_issue(item, "audio_volume_range_abnormal")
        return item


class AudioCleanlinessEvalOperator(BaseOperator):
    operator_name: str = "audio_cleanliness_eval"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        readable = item.get("metrics", {}).get("audio_readable") is True
        volume_ok = item.get("metrics", {}).get("audio_volume_range_ok") is True
        clip_ratio = float(item.get("intermediate", {}).get("audio_clip_ratio") or 0)
        noise_echo_metrics = item.get("intermediate", {}).get("audio_noise_echo_metrics") or {}
        noise_floor_rms = float(noise_echo_metrics.get("noise_floor_rms") or 0)
        snr_db = noise_echo_metrics.get("snr_db")
        silence_ratio = float(noise_echo_metrics.get("silence_ratio") or 0)
        echo_score = float(noise_echo_metrics.get("echo_score") or 0)
        max_clip_ratio = float(self.rules.get("max_audio_clip_ratio", 0.01))
        min_snr_db = float(self.rules.get("min_audio_snr_db", 12.0))
        max_noise_floor_rms = float(self.rules.get("max_audio_noise_floor_rms", 800.0))
        max_silence_ratio = float(self.rules.get("max_audio_silence_ratio", 0.80))
        max_echo_score = float(self.rules.get("max_audio_echo_score", 0.65))
        noise_ok = (snr_db is None or float(snr_db) >= min_snr_db) and noise_floor_rms <= max_noise_floor_rms and silence_ratio <= max_silence_ratio
        echo_ok = echo_score <= max_echo_score
        ok = readable and volume_ok and clip_ratio <= max_clip_ratio and noise_ok and echo_ok
        self.metric(item, "audio_clip_ratio", round(clip_ratio, 6))
        self.metric(item, "audio_noise_floor_rms", round(noise_floor_rms, 4))
        self.metric(item, "audio_snr_db", round(float(snr_db), 4) if isinstance(snr_db, (int, float)) else None)
        self.metric(item, "audio_silence_ratio", round(silence_ratio, 6))
        self.metric(item, "audio_noise_ok", noise_ok)
        self.metric(item, "audio_echo_score", round(echo_score, 6))
        self.metric(item, "audio_echo_ok", echo_ok)
        self.metric(item, "audio_cleanliness_ok", ok)
        if clip_ratio > max_clip_ratio:
            self.add_issue(item, "audio_clipping_detected")
        if not noise_ok:
            self.add_issue(item, "audio_noise_detected")
        if not echo_ok:
            self.add_issue(item, "audio_echo_detected")
        if not ok:
            self.add_issue(item, "audio_cleanliness_abnormal")
        return item


class AudioDupEvalOperator(BaseOperator):
    operator_name: str = "audio_dup_eval"

    def setup(self, items: list[dict[str, Any]], context: dict[str, Any]) -> None:
        seen: dict[str, str] = {}
        duplicates: set[str] = set()
        strategy = str(self.rules.get("audio_duplicate_strategy", "pcm_hash"))
        for item in items:
            path_value = item.get("intermediate", {}).get("audio_path_abs") or item.get("payload", {}).get("audio_path")
            if not path_value:
                continue
            path = Path(str(path_value))
            if not path.exists():
                continue
            try:
                if strategy == "sha256":
                    digest = _file_sha256(path)
                elif strategy == "signature":
                    digest = _file_signature(path)
                else:
                    digest = _audio_content_hash(path)
            except Exception:
                continue
            if digest in seen:
                duplicates.add(str(item["id"]))
                duplicates.add(seen[digest])
            else:
                seen[digest] = str(item["id"])
        self.duplicates = duplicates
        context["audio_duplicate_ids"] = sorted(duplicates)

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        duplicate = str(item.get("id")) in getattr(self, "duplicates", set())
        self.metric(item, "audio_duplicate", duplicate)
        if duplicate:
            self.add_issue(item, "duplicate_audio")
        return item


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_signature(path: Path) -> str:
    stat = path.stat()
    return f"{path.name}:{stat.st_size}"


def _audio_content_hash(path: Path) -> str:
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())
        return _pcm_sha256(channels, sample_width, rate, raw)
    return _file_sha256(path)


def _pcm_sha256(channels: int, sample_width: int, rate: int, raw: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(str(channels).encode("ascii"))
    digest.update(str(sample_width).encode("ascii"))
    digest.update(str(rate).encode("ascii"))
    digest.update(raw)
    return digest.hexdigest()


def _clip_ratio(raw: bytes, sample_width: int, channels: int) -> float:
    if not raw or sample_width not in {1, 2, 3, 4}:
        return 0.0
    max_abs = _max_abs_value(sample_width)
    clipped = 0
    total = 0
    step = sample_width * max(1, channels)
    indexes = range(0, len(raw) - sample_width + 1, step)
    sample_limit = 10000
    stride = max(1, len(raw) // max(sample_width, 1) // sample_limit)
    for index in indexes[::stride]:
        sample = _decode_pcm_sample(raw[index : index + sample_width], sample_width)
        total += 1
        if abs(sample) >= max_abs * 0.98:
            clipped += 1
    return clipped / total if total else 0.0


def _noise_echo_metrics(raw: bytes, sample_width: int, channels: int, rate: int) -> dict[str, float | None]:
    samples = _sampled_mono_samples(raw, sample_width, channels, sample_limit=24000)
    if not samples:
        return {"noise_floor_rms": 0.0, "snr_db": None, "silence_ratio": 0.0, "echo_score": 0.0}

    frame_size = max(32, min(480, int(rate * 0.02) if rate else 480))
    frame_rms = []
    for start in range(0, len(samples), frame_size):
        frame = samples[start : start + frame_size]
        if len(frame) < frame_size // 2:
            continue
        frame_rms.append(math.sqrt(sum(value * value for value in frame) / len(frame)))
    if not frame_rms:
        return {"noise_floor_rms": 0.0, "snr_db": None, "silence_ratio": 0.0, "echo_score": 0.0}

    sorted_rms = sorted(frame_rms)
    low_count = max(1, int(len(sorted_rms) * 0.10))
    high_start = max(0, int(len(sorted_rms) * 0.70))
    noise_floor = sum(sorted_rms[:low_count]) / low_count
    signal_floor = sum(sorted_rms[high_start:]) / max(1, len(sorted_rms) - high_start)
    snr_db = 20 * math.log10((signal_floor + 1.0) / (noise_floor + 1.0))
    silence_threshold = max(50.0, signal_floor * 0.03)
    silence_ratio = sum(1 for value in frame_rms if value <= silence_threshold) / len(frame_rms)
    echo_score = _energy_echo_score(frame_rms)
    return {
        "noise_floor_rms": round(noise_floor, 4),
        "snr_db": round(snr_db, 4),
        "silence_ratio": round(silence_ratio, 6),
        "echo_score": round(echo_score, 6),
    }


def _sampled_mono_samples(raw: bytes, sample_width: int, channels: int, sample_limit: int) -> list[int]:
    if sample_width not in {1, 2, 3, 4} or channels < 1:
        return []
    frame_width = sample_width * channels
    total_frames = len(raw) // frame_width
    if total_frames <= 0:
        return []
    stride = max(1, total_frames // sample_limit)
    samples: list[int] = []
    for frame_index in range(0, total_frames, stride):
        base = frame_index * frame_width
        total = 0
        for channel in range(channels):
            start = base + channel * sample_width
            total += _decode_pcm_sample(raw[start : start + sample_width], sample_width)
        samples.append(int(total / channels))
    return samples


def _energy_echo_score(frame_rms: list[float]) -> float:
    if len(frame_rms) < 20:
        return 0.0
    mean = sum(frame_rms) / len(frame_rms)
    centered = [value - mean for value in frame_rms]
    denom = sum(value * value for value in centered)
    if denom <= 0:
        return 0.0
    best = 0.0
    min_lag = 3
    max_lag = min(25, len(centered) // 2)
    for lag in range(min_lag, max_lag + 1):
        numerator = sum(centered[index] * centered[index - lag] for index in range(lag, len(centered)))
        score = numerator / denom
        if score > best:
            best = score
    return max(0.0, min(best, 1.0))


def _pcm_rms(raw: bytes, sample_width: int) -> int:
    if not raw:
        return 0
    if audioop is not None:
        try:
            return int(audioop.rms(raw, sample_width))
        except Exception:
            pass
    samples = list(_iter_pcm_samples(raw, sample_width))
    if not samples:
        return 0
    return int(math.sqrt(sum(sample * sample for sample in samples) / len(samples)))


def _pcm_minmax(raw: bytes, sample_width: int) -> tuple[int, int]:
    if not raw:
        return (0, 0)
    if audioop is not None:
        try:
            return audioop.minmax(raw, sample_width)
        except Exception:
            pass
    samples = list(_iter_pcm_samples(raw, sample_width))
    return (min(samples), max(samples)) if samples else (0, 0)


def _iter_pcm_samples(raw: bytes, sample_width: int):
    if sample_width not in {1, 2, 3, 4}:
        return
    for index in range(0, len(raw) - sample_width + 1, sample_width):
        yield _decode_pcm_sample(raw[index : index + sample_width], sample_width)


def _decode_pcm_sample(chunk: bytes, sample_width: int) -> int:
    if sample_width == 1:
        return int(chunk[0]) - 128
    if sample_width == 3:
        sign_byte = b"\xff" if chunk[-1] & 0x80 else b"\x00"
        return int.from_bytes(chunk + sign_byte, "little", signed=True)
    return int.from_bytes(chunk, "little", signed=True)


def _max_abs_value(sample_width: int) -> int:
    return 127 if sample_width == 1 else (2 ** (sample_width * 8 - 1)) - 1
