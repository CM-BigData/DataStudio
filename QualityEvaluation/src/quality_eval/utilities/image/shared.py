from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from PIL import Image

from quality_eval.operators.common.base import BaseOperator
from quality_eval.utilities.metrics import action_from_issues, level_from_score, suggestions_for
from quality_eval.utilities.schema import ISSUE_PENALTIES
from quality_eval.runtime.registry import registry

__all__ = [
    "Any",
    "BaseOperator",
    "Image",
    "ISSUE_PENALTIES",
    "Path",
    "action_from_issues",
    "level_from_score",
    "registry",
    "suggestions_for",
    "_average_hash",
    "_grayscale_statistics",
    "_sharpness",
]

def _average_hash(image: Image.Image) -> str:
    """Compute a content hash for an image.

    Business logic:
        1. Convert the image to RGB to remove mode-specific byte differences.
        2. Include the image size in the hash input to avoid false matches across different dimensions.
        3. Feed the RGB pixel bytes into SHA-256 to get a stable content fingerprint.

    Args:
        image (Image.Image): Pillow image object.

    Returns:
        str: SHA-256 fingerprint of the image content.

    Examples:
        >>> img = Image.new("RGB", (1, 1), "white")
        >>> len(_average_hash(img))
        64
    """
    rgb = image.convert("RGB")
    digest = hashlib.sha256()
    digest.update(str(rgb.size).encode("ascii"))
    digest.update(rgb.tobytes())
    return digest.hexdigest()

def _sharpness(image: Image.Image) -> float:
    """Compute image sharpness from adjacent pixel differences.

    Business logic:
        1. Convert the image to grayscale.
        2. Return 0 when width or height is smaller than 2 because adjacent pixels cannot be compared.
        3. Accumulate horizontal and vertical brightness differences between adjacent pixels.
        4. Return the average difference as the sharpness metric.

    Args:
        image (Image.Image): Pillow image object.

    Returns:
        float: Average adjacent-pixel difference; larger values usually mean a sharper image.

    Examples:
        >>> img = Image.new("RGB", (1, 1), "white")
        >>> _sharpness(img)
        0
    """
    gray = image.convert("L")
    values = list(gray.getdata())
    width, height = gray.size
    if width < 2 or height < 2:  # A single-row or single-column image cannot form 2D adjacent-pixel comparisons.
        return 0
    total = 0
    count = 0
    for y in range(height - 1):  # Iterate through each row that can still be compared with the next row.
        offset = y * width
        next_offset = (y + 1) * width
        for x in range(width - 1):  # Compare right and lower neighbors together to estimate local variation.
            current = values[offset + x]
            total += abs(current - values[offset + x + 1])
            total += abs(current - values[next_offset + x])
            count += 2
    return round(total / count, 4)


def _grayscale_statistics(image: Image.Image) -> dict[str, float | int]:
    """Calculate grayscale distribution statistics for an image.

    Business logic:
        1. Convert the image to grayscale so different color modes share one measurement basis.
        2. Calculate pixel count, mean, minimum, maximum, standard deviation, and dynamic range.
        3. Calculate the most common grayscale value ratio to help detect solid or near-solid images.
        4. Return a serializable numeric dictionary that later operators can reuse directly.

    Args:
        image (Image.Image): Pillow image object.

    Returns:
        dict[str, float | int]: Grayscale statistics.

    Examples:
        >>> stats = _grayscale_statistics(Image.new("RGB", (2, 2), "white"))
        >>> stats["dominant_ratio"]
        1.0
    """
    gray = image.convert("L")
    histogram = gray.histogram()
    pixel_count = int(sum(histogram))
    if pixel_count <= 0:  # Empty-pixel images cannot produce valid statistics, so return zeros for downstream fallbacks.
        return {
            "pixel_count": 0,
            "mean_intensity": 0.0,
            "min_intensity": 0,
            "max_intensity": 0,
            "std_intensity": 0.0,
            "dynamic_range": 0,
            "dominant_ratio": 0.0,
        }
    weighted_sum = sum(level * count for level, count in enumerate(histogram))
    mean_intensity = weighted_sum / pixel_count
    variance = sum(((level - mean_intensity) ** 2) * count for level, count in enumerate(histogram)) / pixel_count
    nonzero_levels = [level for level, count in enumerate(histogram) if count > 0]
    min_intensity = min(nonzero_levels)
    max_intensity = max(nonzero_levels)
    dominant_ratio = max(histogram) / pixel_count
    return {
        "pixel_count": pixel_count,
        "mean_intensity": round(mean_intensity, 4),
        "min_intensity": int(min_intensity),
        "max_intensity": int(max_intensity),
        "std_intensity": round(variance ** 0.5, 4),
        "dynamic_range": int(max_intensity - min_intensity),
        "dominant_ratio": round(dominant_ratio, 6),
    }
