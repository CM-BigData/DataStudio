from __future__ import annotations

from pathlib import Path

from denoise_workflow_engine.utilities.image.base import Image


def probe_image_readability(path: Path) -> tuple[bool, int | None]:
    """Check whether one image file is decodable.

    Business logic:
        1. Use Pillow verification when Pillow is available.
        2. Fall back to a byte-size probe when Pillow is unavailable.
        3. Return readability and the fallback byte size when it is collected.

    Args:
        path (Path): Image file path.

    Returns:
        tuple[bool, int | None]: Readability flag and optional byte size.

    Examples:
        >>> callable(probe_image_readability)
        True
    """

    if Image is None:  # Fall back to file-size probing when Pillow is unavailable.
        return True, path.stat().st_size

    with Image.open(path) as image:
        image.verify()

    return True, None


__all__ = ["probe_image_readability"]
