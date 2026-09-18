from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.utilities.network import validate_http_endpoint

try:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
except ImportError:  # pragma: no cover
    Image = None
    ImageEnhance = None
    ImageFilter = None
    ImageOps = None

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

class ImageOperator(BaseOperator):
    def should_skip(self, item: dict) -> bool:
        """Return whether the current sample should skip image processing.

        Business logic:
            1. Read the sample modality and payload fields.
            2. Check whether the sample belongs to image processing.
            3. Return `True` when no usable image payload is present.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            bool: Whether the sample should be skipped.

        Examples:
            >>> should_skip
            should_skip
        """
        return item.get("modality") != "image" and "image_path" not in item.get("payload", {})

    def image_path(self, item: dict) -> Path:
        """Resolve the image path from a sample payload.

        Business logic:
            1. Read the image path value from the payload.
            2. Normalize it into a `Path` object.
            3. Return the resolved path object.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            Path: Image path for the sample.

        Examples:
            >>> image_path
            image_path
        """
        return self.resolve_runtime_path(
            str(item.get("payload", {}).get("image_path", "")),
            name="image path",
        )

def resolve_image_path(path_value: str) -> Path:
    """Convert an image path string into a `Path` object.

    Business logic:
        1. Read the configured path string.
        2. Normalize it through `Path`.
        3. Return the resulting path object.

    Args:
            path_value (str): Configured path string.

    Returns:
        Path: Parsed image path.

    Examples:
        >>> resolve_image_path
        resolve_image_path
    """
    return Path(str(path_value))

def image_to_base64(path: Path, max_side: int = 768) -> str:
    """Compress an image if possible and encode it as base64.

    Business logic:
        1. Read the input image path and size constraint.
        2. Resize and JPEG-encode the image when Pillow is available.
        3. Fall back to raw file bytes when Pillow is unavailable.

    Args:
            path (Path): Image file path.
            max_side (int): Maximum allowed image side length.

    Returns:
        str: Base64-encoded image content.

    Examples:
        >>> image_to_base64
        image_to_base64
    """
    if Image is None:  # Fall back to raw bytes when Pillow is unavailable.
        return base64.b64encode(path.read_bytes()).decode("ascii")
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((max_side, max_side))
        from io import BytesIO

        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=88)
    return base64.b64encode(buffer.getvalue()).decode("ascii")

def extract_json_object(text: str) -> dict[str, Any]:
    """Extract a JSON object from free-form text.

    Business logic:
        1. Trim the input and remove Markdown code fences when present.
        2. Try parsing the full content as JSON.
        3. Fall back to the first brace-delimited object when direct parsing fails.

    Args:
            text (str): Input text content.

    Returns:
        dict[str, Any]: Extracted JSON object, or an empty dict on failure.

    Examples:
        >>> extract_json_object
        extract_json_object
    """
    content = text.strip()
    if content.startswith("```"):  # Strip Markdown fences when the reply is wrapped in a code block.
        content = content.removeprefix("```json").removeprefix("```").strip()
        content = content.removesuffix("```").strip()
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:  # Retry parsing the first brace-delimited JSON object.
            try:
                parsed = json.loads(content[start : end + 1])
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}

class OpenAICompatibleVisionClient:
    def __init__(self, config: dict[str, Any]) -> None:
        """Store OpenAI-compatible vision client configuration.

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
        self.api_key = os.getenv(config.get("api_key_env", "VLM_API_KEY"), config.get("api_key", ""))  # Authentication token for external model requests.
        self.api_base = os.getenv(config.get("api_base_env", "VLM_API_BASE"), config.get("api_base", ""))  # Base URL used to compose the vision endpoint.
        self.model = os.getenv(config.get("model_env", "VLM_MODEL"), config.get("model", ""))  # Model name used for quality, safety, or OCR-related calls.
        self.path = os.getenv(  # OpenAI-compatible vision chat endpoint path.
            config.get("path_env", "VLM_CHAT_COMPLETIONS_PATH"),
            config.get("path", "/v1/chat/completions"),
        )
        self.timeout = float(config.get("timeout", 60))  # Maximum wait time for external API calls, in seconds.
        self.temperature = float(config.get("temperature", 0))  # Sampling temperature; defaults to 0 to reduce drift on the same image.
        self.max_tokens = int(config.get("max_tokens", 800))  # Upper bound on response length to keep JSON outputs concise.

    def is_enabled(self) -> bool:
        """Return whether the external vision client is fully configured.

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

    def chat_json(self, image_path: Path, prompt: str) -> tuple[dict[str, Any], str]:
        """Call an OpenAI-compatible vision API and parse a JSON response.

        Business logic:
            1. Encode the image and assemble the outbound model request.
            2. Send the request and read the JSON response.
            3. Return the parsed object and any error message.

        Args:
                image_path (Path): Image file path.
                prompt (str): Prompt text sent to the vision model.

        Returns:
            tuple[dict[str, Any], str]: Parsed JSON object and error string.

        Examples:
            >>> chat_json
            chat_json
        """
        try:
            image_b64 = image_to_base64(image_path, int(self.config.get("max_side", 768)))
        except Exception as exc:
            return {}, f"image_encode_failed: {exc}"
        endpoint = self._endpoint()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            import requests

            response = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except Exception as exc:
            return {}, str(exc)
        parsed = extract_json_object(str(content))
        if not parsed:  # Trigger local fallback when the model reply is not valid JSON.
            return {}, "invalid_json_response"
        return parsed, ""

    def _endpoint(self) -> str:
        """Build the final vision endpoint URL.

        Business logic:
            1. Read the configured API base URL.
            2. Reuse it directly when it already points at the chat completions endpoint.
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
        if base.endswith("/chat/completions"):  # Reuse the URL directly when it already targets chat completions.
            endpoint = base
        else:
            endpoint = base + "/" + self.path.lstrip("/")
        return validate_http_endpoint(endpoint, "vision API endpoint")

def bounded_float(value: Any, default: float = 0.0) -> float:
    """Convert and clamp a score-like value into the range [0, 1].

    Business logic:
        1. Try converting the input into a float.
        2. Clamp the parsed value into the valid score range.
        3. Return the provided default when conversion fails.

    Args:
            value (Any): Value to normalize.
            default (float): Default value returned on failure.

    Returns:
        float: Normalized score.

    Examples:
        >>> bounded_float
        bounded_float
    """
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default

def edge_density(gray_array: Any) -> float:
    """Compute a simple edge-density score from a grayscale array.

    Business logic:
        1. Convert the array into float form.
        2. Measure horizontal and vertical pixel differences.
        3. Return the normalized average edge magnitude.

    Args:
            gray_array (Any): Grayscale image array.

    Returns:
        float: Edge-density score.

    Examples:
        >>> edge_density
        edge_density
    """
    if np is None:  # Return a neutral score when NumPy is unavailable.
        return 0.0
    arr = gray_array.astype("float32")
    gx = np.abs(np.diff(arr, axis=1)).mean() if arr.shape[1] > 1 else 0.0
    gy = np.abs(np.diff(arr, axis=0)).mean() if arr.shape[0] > 1 else 0.0
    return float((gx + gy) / 510.0)

def image_entropy(gray_array: Any) -> float:
    """Compute a coarse image-entropy score from a grayscale array.

    Business logic:
        1. Build a histogram over grayscale values.
        2. Compute the entropy of non-zero histogram bins.
        3. Return the normalized entropy score.

    Args:
            gray_array (Any): Grayscale image array.

    Returns:
        float: Image-entropy score.

    Examples:
        >>> image_entropy
        image_entropy
    """
    if np is None:  # Return a neutral score when NumPy is unavailable.
        return 0.0
    hist, _ = np.histogram(gray_array, bins=32, range=(0, 255), density=True)
    hist = hist[hist > 0]
    return float(-(hist * np.log2(hist)).sum() / 5.0)
