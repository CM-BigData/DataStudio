from __future__ import annotations

import base64
import json
import math
import os
import regex as re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from statistics import mean
from typing import Any

ROOT = Path.cwd()  # Base directory used by video operators to resolve relative workflow assets and outputs.

from PIL import Image

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.runtime.loader import safe_child_path, validate_path_component
from denoise_workflow_engine.utilities.image.base import OpenAICompatibleVisionClient, bounded_float, extract_json_object
from denoise_workflow_engine.utilities.network import validate_http_endpoint

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


root_path = ROOT

def ffmpeg_path() -> str:
    """Locate the ffmpeg executable.

    Business logic:
        1. Look up `ffmpeg` on the system path.
        2. Fall back to the bundled Windows-style path when needed.
        3. Return the resolved executable path string.

    Args:
            None: This function does not take input parameters.

    Returns:
        str: Resolved ffmpeg executable path.

    Examples:
        >>> ffmpeg_path
        ffmpeg_path
    """
    return shutil.which("ffmpeg") or str(Path(r"E:\anaconda\Library\bin\ffmpeg.exe"))

def ffprobe_path() -> str:
    """Locate the ffprobe executable.

    Business logic:
        1. Look up `ffprobe` on the system path.
        2. Fall back to the bundled Windows-style path when needed.
        3. Return the resolved executable path string.

    Args:
            None: This function does not take input parameters.

    Returns:
        str: Resolved ffprobe executable path.

    Examples:
        >>> ffprobe_path
        ffprobe_path
    """
    return shutil.which("ffprobe") or str(Path(r"E:\anaconda\Library\bin\ffprobe.exe"))

class OpenAICompatibleAudioClient:
    def __init__(self, config: dict[str, Any]) -> None:
        """Store OpenAI-compatible audio client configuration.

        Business logic:
            1. Read runtime configuration and environment overrides.
            2. Store reusable API connection settings.
            3. Keep construction side-effect free.

        Args:
                config (dict[str, Any]): Client configuration dictionary.

        Returns:
            None: The constructor initializes the client in place.

        Examples:
            >>> __init__
            __init__
        """
        self.config = config  # Runtime configuration such as thresholds, endpoints, and API parameters.
        self.api_key = os.getenv(config.get("api_key_env", "ASR_API_KEY"), config.get("api_key", ""))  # Authentication token for external audio transcription calls.
        self.api_base = os.getenv(config.get("api_base_env", "ASR_API_BASE"), config.get("api_base", ""))  # Base URL used to compose the transcription endpoint.
        self.model = os.getenv(config.get("model_env", "ASR_MODEL"), config.get("model", ""))  # Model name used for transcription and related audio checks.
        self.path = os.getenv(config.get("path_env", "ASR_TRANSCRIPTIONS_PATH"), config.get("path", "/v1/audio/transcriptions"))  # OpenAI-compatible audio transcription endpoint path.
        self.timeout = float(config.get("timeout", 60))  # Maximum wait time for external API calls, in seconds.
        self.temperature = float(config.get("temperature", 0))  # Sampling temperature; defaults to 0 for stable transcription results.
        self.max_tokens = int(config.get("max_tokens", 800))  # Upper bound on transcription response length.

    def is_enabled(self) -> bool:
        """Return whether the external audio client is fully configured.

        Business logic:
            1. Read the required API key, base URL, and model settings.
            2. Check whether all required values are non-empty.
            3. Return the availability flag.

        Args:
                None: This method does not take input parameters.

        Returns:
            bool: Whether the external client can be called.

        Examples:
            >>> is_enabled
            is_enabled
        """
        return bool(self.api_key and self.api_base and self.model)

    def transcribe_json(self, audio_path: Path, prompt: str = "") -> tuple[dict[str, Any], str]:
        """Call an audio transcription API and parse the structured response.

        Business logic:
            1. Encode the audio payload and assemble the request body.
            2. Send the request and decode the returned JSON.
            3. Return a structured result together with any error message.

        Args:
                audio_path (Path): Audio file path.
                prompt (str): Optional transcription prompt.

        Returns:
            tuple[dict[str, Any], str]: Parsed response object and error string.

        Examples:
            >>> transcribe_json
            transcribe_json
        """
        try:
            audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        except Exception as exc:
            return {}, f"audio_encode_failed: {exc}"
        payload = {
            "model": self.model,
            "audio_base64": audio_b64,
            "file_name": audio_path.name,
            "prompt": prompt,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        request = urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            # `_endpoint` restricts the request target to a validated HTTP(S) URL.
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # nosec B310
                data = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {}, str(exc)
        if isinstance(data, dict) and ("text" in data or "asr_text" in data):  # Accept direct text-like transcription payloads.
            return data, ""
        if isinstance(data, dict) and data.get("choices"):  # Also support chat-style response envelopes.
            try:
                content = data["choices"][0]["message"]["content"]
                parsed = extract_json_object(str(content))
                return parsed if parsed else {"asr_text": str(content)}, ""
            except Exception as exc:
                return {}, f"unexpected_response: {exc}"
        return data if isinstance(data, dict) else {}, ""

    def _endpoint(self) -> str:
        """Build the final audio endpoint URL.

        Business logic:
            1. Read the configured API base URL.
            2. Reuse it directly when it already points at the audio transcription endpoint.
            3. Otherwise append the configured path.

        Args:
                None: This method does not take input parameters.

        Returns:
            str: Final endpoint URL.

        Examples:
            >>> _endpoint
            _endpoint
        """
        base = self.api_base.rstrip("/")
        if base.endswith("/audio/transcriptions"):  # Reuse the URL directly when it already targets audio transcriptions.
            endpoint = base
        else:
            endpoint = base + "/" + self.path.lstrip("/")
        return validate_http_endpoint(endpoint, "audio API endpoint")

class VideoOperator(BaseOperator):
    def should_skip(self, item: dict) -> bool:
        """Return whether the current sample should skip video processing.

        Business logic:
            1. Read the sample modality and payload fields.
            2. Check whether the sample belongs to video processing.
            3. Return `True` when no usable video payload is present.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            bool: Whether the sample should be skipped.

        Examples:
            >>> should_skip
            should_skip
        """
        return item.get("modality") != "video" and "video_path" not in item.get("payload", {})

    def video_path(self, item: dict) -> Path:
        """Resolve the video path from a sample payload.

        Business logic:
            1. Read the video path value from the payload.
            2. Normalize it into a `Path` object.
            3. Resolve relative paths against the operator root path.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            Path: Video path for the sample.

        Examples:
            >>> video_path
            video_path
        """
        return self.resolve_runtime_path(
            str(item.get("payload", {}).get("video_path", "")),
            name="video path",
        )

    def run_dir(self, item: dict, name: str) -> Path:
        """Create or reuse an intermediate artifact directory for a sample.

        Business logic:
            1. Read the sample ID and requested artifact subdirectory name.
            2. Build a stable run directory path under the video artifact root.
            3. Create the directory and return it.

        Args:
                item (dict): Current sample dictionary.
                name (str): Artifact subdirectory name.

        Returns:
            Path: Created artifact directory path.

        Examples:
            >>> run_dir
            run_dir
        """
        intermediate = item.setdefault("intermediate", {})
        existing_run_id = intermediate.get("video_run_id")
        if existing_run_id:
            run_id = validate_path_component(existing_run_id, "video run id")
        else:
            run_id = f"{self.safe_item_id(item, 'video')}_{time.time_ns()}"
            intermediate["video_run_id"] = run_id
        artifact_root = safe_child_path(self.runtime_run_dir(), "_video_artifacts", "video artifact directory")
        sample_root = safe_child_path(artifact_root, run_id, "video sample directory")
        path = safe_child_path(sample_root, validate_path_component(name, "video artifact name"), "video artifact path")
        path.mkdir(parents=True, exist_ok=True)
        return path

def parse_fps(value: str) -> float:
    """Parse an ffprobe frame-rate string into a float.

    Business logic:
        1. Detect fraction-form frame-rate strings.
        2. Parse numerator and denominator when needed.
        3. Return the resulting float frame rate or 0.0 on failure.

    Args:
            value (str): Value to parse.

    Returns:
        float: Parsed frame rate.

    Examples:
        >>> parse_fps
        parse_fps
    """
    if "/" in value:  # Parse ffprobe-style fractional frame-rate strings.
        left, right = value.split("/", 1)
        try:
            return float(left) / max(float(right), 1.0)
        except ValueError:
            return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0

def has_any_issue(item: dict, issues: set[str]) -> bool:
    """Return whether a sample contains any issue from the target set.

    Business logic:
        1. Read the sample issue list.
        2. Intersect it with the target issue set.
        3. Return whether any overlap exists.

    Args:
            item (dict): Current sample dictionary.
            issues (set[str]): Target issue-tag set.

    Returns:
        bool: Whether any target issue is present.

    Examples:
        >>> has_any_issue
        has_any_issue
    """
    return bool(set(item.get("issues", [])) & issues)

def frame_sharpness(pixels: list[int], width: int) -> float:
    """Estimate frame sharpness from grayscale pixels.

    Business logic:
        1. Traverse grayscale pixels row by row.
        2. Measure horizontal and vertical edge differences.
        3. Return the average edge strength as a sharpness score.

    Args:
            pixels (list[int]): Pixel sequence.
            width (int): Image width.

    Returns:
        float: Estimated frame sharpness.

    Examples:
        >>> frame_sharpness
        frame_sharpness
    """
    diffs = []
    for idx, pixel in enumerate(pixels):  # Traverse grayscale pixels to estimate horizontal and vertical edge strength.
        if idx % width != width - 1:  # Skip the last pixel in each row to avoid wraparound edge differences.
            diffs.append(abs(pixel - pixels[idx + 1]))
        if idx + width < len(pixels):  # Compare against the pixel below when it exists.
            diffs.append(abs(pixel - pixels[idx + width]))
    return mean(diffs) if diffs else 0.0

def local_noise_score(pixels: list[int], width: int) -> float:
    """Estimate frame noise from local pixel residuals.

    Business logic:
        1. Traverse interior pixels only.
        2. Compare each center pixel to the average of its four neighbors.
        3. Return the mean residual magnitude as a noise score.

    Args:
            pixels (list[int]): Pixel sequence.
            width (int): Image width.

    Returns:
        float: Estimated frame noise.

    Examples:
        >>> local_noise_score
        local_noise_score
    """
    residuals = []
    for y in range(1, width - 1):  # Skip border pixels so vertical neighbors exist.
        for x in range(1, width - 1):  # Compute center-pixel residuals within each row.
            idx = y * width + x
            neighbors = [pixels[idx - 1], pixels[idx + 1], pixels[idx - width], pixels[idx + width]]
            residuals.append(abs(pixels[idx] - mean(neighbors)))
    return mean(residuals) if residuals else 0.0

def parse_volume(output: str, key: str) -> float | None:
    """Parse a loudness metric from ffmpeg volumedetect output.

    Business logic:
        1. Search the command output for the requested volume key.
        2. Extract the numeric dB value when present.
        3. Return `None` when the target field is missing.

    Args:
            output (str): Command output.
            key (str): Metric key.

    Returns:
        float | None: Parsed loudness metric.

    Examples:
        >>> parse_volume
        parse_volume
    """
    match = re.search(rf"{key}:\s*(-?\d+(?:\.\d+)?)\s*dB", output)
    if not match:  # Return no metric when the target field is absent.
        return None
    return float(match.group(1))

def as_list(value: Any) -> list[str]:
    """Normalize a value into a list of strings.

    Business logic:
        1. Return an empty list for missing values.
        2. Normalize existing lists and comma-separated strings.
        3. Wrap any other scalar into a one-element string list.

    Args:
            value (Any): Value to normalize.

    Returns:
        list[str]: Normalized string list.

    Examples:
        >>> as_list
        as_list
    """
    if value is None:  # Return an empty list when the value is missing.
        return []
    if isinstance(value, list):  # Normalize list values element by element.
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):  # Normalize string values directly.
        if "," in value:  # Split comma-separated config strings into multiple tokens.
            return [part.strip() for part in value.split(",") if part.strip()]
        return [value] if value.strip() else []
    return [str(value)]

def normalize_tokens(text: str) -> set[str]:
    """Normalize free-form text into a token set.

    Business logic:
        1. Lowercase the text and split on non-semantic separators.
        2. Strip token punctuation and whitespace.
        3. Return the resulting token set.

    Args:
            text (str): Input text content.

    Returns:
        set[str]: Normalized text tokens.

    Examples:
        >>> normalize_tokens
        normalize_tokens
    """
    tokens = set()
    for token in re.split(r"[^A-Za-z0-9\u4e00-\u9fff]+", str(text).lower()):  # Split video-text keywords on non-semantic separators.
        token = token.strip("_- ")
        if token:  # Keep only non-empty tokens.
            tokens.add(token)
    return tokens

def token_overlap(left: str, right: str) -> float:
    """Compute token overlap between two text strings.

    Business logic:
        1. Normalize both texts into token sets.
        2. Compute their intersection size.
        3. Return overlap relative to the left-side token count.

    Args:
            left (str): Left-side text.
            right (str): Right-side text.

    Returns:
        float: Token-overlap score.

    Examples:
        >>> token_overlap
        token_overlap
    """
    left_tokens = normalize_tokens(left)
    right_tokens = normalize_tokens(right)
    if not left_tokens or not right_tokens:  # Return zero similarity when either side has no valid tokens.
        return 0.0
    return len(left_tokens & right_tokens) / max(len(left_tokens), 1)

def rel_to_root(path: Path) -> str:
    """Convert a path into a project-relative POSIX string when possible.

    Business logic:
        1. Try converting the path relative to the project root.
        2. Fall back to the absolute path when relative conversion fails.
        3. Normalize path separators to POSIX style.

    Args:
            path (Path): File path.

    Returns:
        str: Project-relative or normalized path string.

    Examples:
        >>> rel_to_root
        rel_to_root
    """
    try:
        return path.relative_to(root_path).as_posix()
    except ValueError:
        return str(path).replace("\\", "/")
