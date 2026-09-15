from __future__ import annotations

import hashlib
import math
import wave
from itertools import combinations
from pathlib import Path
from typing import Any

from dedup_workflow_engine.operators.base import BaseOperator
from dedup_workflow_engine.utilities.vector import (
    bytes_hashing_vector,
    call_json_api_endpoint,
    config_enabled,
    cosine_similarity,
    missing_env_names,
    pairwise_topk,
)
from dedup_workflow_engine.utilities.text.normalize import normalize_text
from dedup_workflow_engine.operators.text_dedup.simhash import hamming_distance, simhash

def file_sha256(path: Path) -> str:
    """Compute SHA-256 for an audio file.

    Business logic:
        1. Open the audio file in binary mode.
        2. Update the digest in 1 MB chunks.
        3. Return the hexadecimal SHA-256 string.

    Args:
        path (Path): Audio file path.

    Returns:
        str: File SHA-256 hex digest.

    Examples:
        >>> file_sha256(Path("audio.wav"))  # doctest: +SKIP
        'abc'
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):  # Read in chunks to avoid loading large audio files into memory at once.
            digest.update(chunk)
    return digest.hexdigest()

def read_wav_metadata(path: Path) -> dict[str, Any] | None:
    """Read basic metadata from a WAV file.

    Business logic:
        1. Open the WAV file with the wave module.
        2. Read frame count, sample rate, channel count, and sample width.
        3. Compute duration in seconds and return a metadata dictionary.

    Args:
        path (Path): WAV file path.

    Returns:
        dict[str, Any] | None: WAV metadata, or None when reading fails.

    Examples:
        >>> read_wav_metadata(Path("audio.wav"))  # doctest: +SKIP
        {'sample_rate': 16000}
    """
    try:
        with wave.open(str(path), "rb") as wav:
            frames = wav.getnframes()
            rate = wav.getframerate()
            return {
                "sample_rate": rate,
                "channels": wav.getnchannels(),
                "sample_width": wav.getsampwidth(),
                "duration_seconds": round(frames / rate, 3) if rate else 0,
            }
    except Exception:
        return None

def wav_pcm_sha256(path: Path) -> str | None:
    """Compute a hash for WAV PCM content.

    Business logic:
        1. Include channel count, sample width, and sample rate in the digest.
        2. Read PCM frames in chunks and update the digest.
        3. Return None when WAV reading fails.

    Args:
        path (Path): WAV file path.

    Returns:
        str | None: PCM-content hash, or None when reading fails.

    Examples:
        >>> wav_pcm_sha256(Path("audio.wav"))  # doctest: +SKIP
        'abc'
    """
    digest = hashlib.sha256()
    try:
        with wave.open(str(path), "rb") as wav:
            digest.update(str(wav.getnchannels()).encode("ascii"))
            digest.update(str(wav.getsampwidth()).encode("ascii"))
            digest.update(str(wav.getframerate()).encode("ascii"))
            while True:  # Keep reading PCM frames until wave returns empty bytes.
                frames = wav.readframes(4096)
                if not frames:  # Empty frames mean the file end has been reached.
                    break
                digest.update(frames)
    except Exception:
        return None
    return digest.hexdigest()

def wav_samples(path: Path, return_rate: bool = False) -> list[int] | tuple[list[int], int | None]:
    """Read first-channel sample values from a WAV file.

    Business logic:
        1. Read sample width, channel count, sample rate, and all frames from the WAV file.
        2. Extract first-channel samples using frame-step traversal.
        3. Return the sample rate together with samples when return_rate is enabled.

    Args:
        path (Path): WAV file path.
        return_rate (bool, optional): Whether to return sample rate. Defaults to False.

    Returns:
        list[int] | tuple[list[int], int | None]: Sample list, or sample list plus sample rate.

    Examples:
        >>> wav_samples(Path("audio.wav"))  # doctest: +SKIP
        [0]
    """
    try:
        with wave.open(str(path), "rb") as wav:
            width = wav.getsampwidth()
            channels = wav.getnchannels()
            rate = wav.getframerate()
            raw = wav.readframes(wav.getnframes())
    except Exception:
        return ([], None) if return_rate else []
    samples = []
    step = width * channels
    for index in range(0, len(raw) - step + 1, step):  # Advance by one full frame each time and read only the first channel.
        channel_bytes = raw[index : index + width]
        if width == 1:  # 8-bit PCM is typically unsigned and needs to be shifted to an approximately signed value.
            value = channel_bytes[0] - 128
        else:
            value = int.from_bytes(channel_bytes[:2], "little", signed=True)
        samples.append(value)
    if return_rate:  # Acoustic features need sample rate to convert bins into frequencies.
        return samples, rate
    return samples

def wav_energy_fingerprint(path: Path, bins: int = 64) -> str:
    """Generate a WAV energy-fingerprint string.

    Business logic:
        1. Read sample values and sample rate.
        2. Compute a fixed-bin frequency signature.
        3. Binarize it into a 0/1 string using average energy.

    Args:
        path (Path): WAV file path.
        bins (int, optional): Number of fingerprint bins. Defaults to 64.

    Returns:
        str: Binarized energy fingerprint, or an empty string when reading fails.

    Examples:
        >>> wav_energy_fingerprint(Path("audio.wav"))  # doctest: +SKIP
        '0101'
    """
    samples, rate = wav_samples(path, return_rate=True)
    if not samples:  # No frequency signature can be generated when sample values are missing.
        return ""
    features = frequency_signature(samples, rate or 16000, bins)
    average = sum(features) / len(features)
    return "".join("1" if value >= average else "0" for value in features)

def wav_acoustic_vector(path: Path, bins: int = 64) -> list[float]:
    """Generate a WAV acoustic feature vector.

    Business logic:
        1. Read sample values and sample rate.
        2. Compute spectral signature, RMS, and zero-crossing rate.
        3. Concatenate them and apply L2 normalization.

    Args:
        path (Path): WAV file path.
        bins (int, optional): Number of bins per feature type. Defaults to 64.

    Returns:
        list[float]: Acoustic feature vector, or an empty list when reading fails.

    Examples:
        >>> wav_acoustic_vector(Path("audio.wav"))  # doctest: +SKIP
        [0.0]
    """
    samples, rate = wav_samples(path, return_rate=True)
    if not samples:  # Acoustic features cannot be computed when sample values are missing.
        return []
    rate = rate or 16000
    spectral = frequency_signature(samples, rate, bins)
    rms = frame_rms(samples, bins)
    zcr = frame_zero_crossing(samples, bins)
    vector = []
    for index in range(bins):  # Concatenate spectral, energy, and zero-crossing features for each bin.
        vector.append(spectral[index] if index < len(spectral) else 0.0)
        vector.append(rms[index] if index < len(rms) else 0.0)
        vector.append(zcr[index] if index < len(zcr) else 0.0)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:  # Zero vectors cannot be normalized, so keep the original values.
        return vector
    return [value / norm for value in vector]

def frequency_signature(samples: list[int], rate: int, bins: int = 64) -> list[float]:
    """Compute a fixed frequency signature from sample values.

    Business logic:
        1. Build target frequencies across the Nyquist range.
        2. Estimate each frequency magnitude with the Goertzel algorithm.
        3. Normalize the signature by its maximum magnitude.

    Args:
        samples (list[int]): PCM sample values.
        rate (int): Sample rate.
        bins (int, optional): Number of frequency bins. Defaults to 64.

    Returns:
        list[float]: Normalized frequency signature.

    Examples:
        >>> frequency_signature([], 16000)
        []
    """
    if not samples:  # No frequency signature exists when sample values are missing.
        return []
    frequencies = [rate * (index + 1) / (2 * bins) for index in range(bins)]
    signature = [goertzel_magnitude(samples, rate, frequency) for frequency in frequencies]
    max_value = max(signature) or 1.0
    return [value / max_value for value in signature]

def goertzel_magnitude(samples: list[int], rate: int, frequency: float) -> float:
    """Estimate the magnitude of a target frequency with the Goertzel algorithm.

    Business logic:
        1. Validate samples, sample rate, and target frequency.
        2. Iteratively update Goertzel states q0, q1, and q2.
        3. Convert the final state into a frequency magnitude.

    Args:
        samples (list[int]): PCM sample values.
        rate (int): Sample rate.
        frequency (float): Target frequency.

    Returns:
        float: Target-frequency magnitude.

    Examples:
        >>> goertzel_magnitude([], 16000, 440.0)
        0.0
    """
    if not samples or rate <= 0 or frequency <= 0:  # Invalid input cannot produce a frequency magnitude.
        return 0.0
    omega = 2 * math.pi * frequency / rate
    cosine = math.cos(omega)
    sine = math.sin(omega)
    coeff = 2 * cosine
    q0 = q1 = q2 = 0.0
    for sample in samples:  # Update the Goertzel recurrence state once for each sample point.
        q0 = coeff * q1 - q2 + sample
        q2 = q1
        q1 = q0
    real = q1 - q2 * cosine
    imag = q2 * sine
    return math.sqrt(real * real + imag * imag)

def frame_rms(samples: list[int], bins: int) -> list[float]:
    """Compute frame-level RMS energy features.

    Business logic:
        1. Compute frame size from sample length and bins.
        2. Compute root-mean-square energy for each frame.
        3. Pad to bins length and normalize by the maximum value.

    Args:
        samples (list[int]): PCM sample values.
        bins (int): Number of output bins.

    Returns:
        list[float]: Normalized RMS features.

    Examples:
        >>> frame_rms([], 4)
        []
    """
    if not samples:  # No RMS features exist when sample values are missing.
        return []
    frame_size = max(1, len(samples) // bins)
    output = []
    for start in range(0, len(samples), frame_size):  # Traverse sample values using a fixed frame size.
        frame = samples[start : start + frame_size]
        if not frame:  # Defensively skip empty frames.
            continue
        output.append(math.sqrt(sum(value * value for value in frame) / len(frame)))
        if len(output) >= bins:  # Stop after reaching the target number of bins.
            break
    while len(output) < bins:  # Pad short audio with zeros to the target feature length.
        output.append(0.0)
    max_value = max(output) or 1.0
    return [value / max_value for value in output]

def frame_zero_crossing(samples: list[int], bins: int) -> list[float]:
    """Compute frame-level zero-crossing-rate features.

    Business logic:
        1. Compute frame size from sample length and bins.
        2. Measure the proportion of sign changes for each frame.
        3. Pad to bins length and return the result.

    Args:
        samples (list[int]): PCM sample values.
        bins (int): Number of output bins.

    Returns:
        list[float]: Zero-crossing rate for each frame.

    Examples:
        >>> frame_zero_crossing([], 4)
        []
    """
    if not samples:  # No zero-crossing-rate features exist when sample values are missing.
        return []
    frame_size = max(1, len(samples) // bins)
    output = []
    for start in range(0, len(samples), frame_size):  # Traverse sample values using a fixed frame size.
        frame = samples[start : start + frame_size]
        if len(frame) < 2:  # A single-sample frame has no sign changes.
            output.append(0.0)
        else:
            crossings = sum(1 for index in range(1, len(frame)) if (frame[index - 1] < 0) != (frame[index] < 0))
            output.append(crossings / len(frame))
        if len(output) >= bins:  # Stop after reaching the target number of bins.
            break
    while len(output) < bins:  # Pad short audio with zeros to the target feature length.
        output.append(0.0)
    return output

def string_similarity(left: str, right: str) -> float:
    """Compute position-wise similarity between two equalized fingerprint strings.

    Business logic:
        1. Use the shorter string length as the comparison range.
        2. Count character matches at the same positions.
        3. Divide the match count by the longer string length.

    Args:
        left (str): Left fingerprint string.
        right (str): Right fingerprint string.

    Returns:
        float: Position-wise similarity between 0 and 1.

    Examples:
        >>> string_similarity("101", "100")
        0.6666666666666666
    """
    size = min(len(left), len(right))
    if size == 0:  # There is no string-similarity evidence when either side is empty.
        return 0.0
    matches = sum(1 for index in range(size) if left[index] == right[index])
    return matches / max(len(left), len(right))

def fuse_audio_edges(edges: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    """Fuse audio duplicate candidate edges.

    Business logic:
        1. Merge candidate edges by undirected sample pair.
        2. Apply audio_reason_weight to scores from different sources.
        3. Keep the highest score, all reasons, and the strongest duplicate_type.

    Args:
        edges (list[dict[str, Any]]): Candidate edges generated by upstream audio operators.
        weights (dict[str, float]): Fusion weights for audio deduplication signals.

    Returns:
        list[dict[str, Any]]: Fused audio duplicate edge list.

    Examples:
        >>> fuse_audio_edges([], {})
        []
    """
    fused = {}
    for edge in edges:  # Aggregate every candidate edge by undirected pair.
        key = tuple(sorted([str(edge["left_id"]), str(edge["right_id"])]))
        reasons = edge.get("reasons", [edge.get("reason", "unknown")])
        score = float(edge.get("score", 0)) * audio_reason_weight(reasons, weights)
        if key not in fused:  # Create the fused record immediately for a new pair.
            fused[key] = {
                "left_id": key[0],
                "right_id": key[1],
                "score": score,
                "duplicate_type": edge.get("duplicate_type", "near_duplicate"),
                "reasons": list(reasons),
                "operators": edge.get("operators", [edge.get("operator", "AudioDupFusionOperator")]),
            }
            continue
        fused_edge = fused[key]
        fused_edge["score"] = max(float(fused_edge["score"]), score)
        for reason in reasons:  # Preserve every audio-duplicate evidence source for the same pair.
            if reason not in fused_edge["reasons"]:  # Do not write reasons that are already present.
                fused_edge["reasons"].append(reason)
        if edge.get("duplicate_type") == "exact_duplicate":  # exact_duplicate has the highest priority.
            fused_edge["duplicate_type"] = "exact_duplicate"
        elif edge.get("duplicate_type") == "semantic_duplicate" and fused_edge["duplicate_type"] != "exact_duplicate":
            fused_edge["duplicate_type"] = "semantic_duplicate"
    return list(fused.values())

def audio_reason_weight(reasons: list[str], weights: dict[str, float]) -> float:
    """Choose a fusion weight from audio duplicate reasons.

    Business logic:
        1. Traverse candidate-edge reasons.
        2. Match sources such as exact, pcm, fingerprint, acoustic, embedding, and asr.
        3. Return the highest weight among all matched sources.

    Args:
        reasons (list[str]): Duplicate-reason list for a candidate edge.
        weights (dict[str, float]): Weight config for audio deduplication signals.

    Returns:
        float: Fusion weight applied to the candidate edge.

    Examples:
        >>> audio_reason_weight(["audio_embedding_cosine>=0.9"], {"embedding": 0.9})
        1.0
    """
    score = 1.0
    for reason in reasons:  # Each reason may correspond to one audio-deduplication signal.
        lower = reason.lower()
        if "exact" in lower:  # Exact signals such as file hashes use exact_hash weight.
            score = max(score, float(weights.get("exact_hash", 1.0)))
        elif "pcm" in lower:
            score = max(score, float(weights.get("pcm", 1.0)))
        elif "fingerprint" in lower:
            score = max(score, float(weights.get("fingerprint", 1.0)))
        elif "acoustic" in lower or "mfcc" in lower:
            score = max(score, float(weights.get("acoustic", 1.0)))
        elif "embedding" in lower:
            score = max(score, float(weights.get("embedding", 1.0)))
        elif "asr" in lower:
            score = max(score, float(weights.get("asr", 1.0)))
    return score
