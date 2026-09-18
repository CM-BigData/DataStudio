from __future__ import annotations

import hashlib
import re
from itertools import combinations
from pathlib import Path
from typing import Any

from dedup_workflow_engine.utilities.vector import (
    bytes_hashing_vector,
    call_json_api_endpoint,
    config_enabled,
    cosine_similarity,
    missing_env_names,
    pairwise_topk,
)
from dedup_workflow_engine.operators.base import BaseOperator

def file_sha256(path: Path) -> str:
    """Compute SHA-256 for an image file.

    Business logic:
        1. Open the file in binary mode.
        2. Update the digest in 1 MB chunks.
        3. Return the hexadecimal SHA-256 string.

    Args:
        path (Path): Image file path.

    Returns:
        str: File SHA-256 hex digest.

    Examples:
        >>> file_sha256(Path("image.png"))  # doctest: +SKIP
        'abc'
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):  # Read in chunks to avoid loading large images into memory at once.
            digest.update(chunk)
    return digest.hexdigest()

def image_dimensions(path: Path) -> tuple[int, int] | None:
    """Read image width and height.

    Business logic:
        1. Prefer Pillow for reading actual image dimensions.
        2. Fall back to reading P3 PPM when Pillow is unavailable or decoding fails.
        3. Return None when both methods fail.

    Args:
        path (Path): Image file path.

    Returns:
        tuple[int, int] | None: Image width and height, or None when reading fails.

    Examples:
        >>> image_dimensions(Path("image.ppm"))  # doctest: +SKIP
        (10, 10)
    """
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            return image.size
    except Exception:
        ppm = read_ppm(path)
        if ppm is None:  # Dimensions are unavailable when both Pillow and the PPM fallback fail.
            return None
        width, height, _pixels = ppm
        return width, height
    ppm = read_ppm(path)
    if ppm is None:  # Files unreadable by Pillow and not valid P3 PPM have no usable dimensions.
        return None
    width, height, _pixels = ppm
    return width, height

def load_grayscale_vector(path: Path, max_side: int = 64) -> list[float]:
    """Read an image and generate a fixed-size grayscale vector.

    Business logic:
        1. Prefer Pillow to convert to grayscale and resize to max_side.
        2. Parse P3 PPM and apply nearest-neighbor sampling when Pillow fails.
        3. Return grayscale values in the range 0 to 1.

    Args:
        path (Path): Image file path.
        max_side (int, optional): Output grayscale side length. Defaults to 64.

    Returns:
        list[float]: Fixed-size grayscale vector, or an empty list when reading fails.

    Examples:
        >>> load_grayscale_vector(Path("image.png"))  # doctest: +SKIP
        [0.0]
    """
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            grayscale = image.convert("L")
            grayscale.thumbnail((max_side, max_side))
            resized = grayscale.resize((max_side, max_side))
            return [value / 255.0 for value in resized.getdata()]
    except Exception:
        ppm = read_ppm(path)
        if ppm is None:  # Return an empty vector when no image-decoding path is available.
            return []
        width, height, pixels = ppm
        values = []
        for y in range(max_side):  # Sample source pixels by output row.
            src_y = min(height - 1, int(y * height / max_side))
            for x in range(max_side):  # Sample source pixels by output column.
                src_x = min(width - 1, int(x * width / max_side))
                r, g, b = pixels[src_y * width + src_x]
                values.append((0.299 * r + 0.587 * g + 0.114 * b) / 255.0)
        return values

def simple_ssim(left: list[float], right: list[float]) -> float:
    """Compute a simplified SSIM score for two grayscale vectors.

    Business logic:
        1. Align both vectors to their shared length.
        2. Compute means, variances, and covariance.
        3. Return structural similarity using the SSIM formula.

    Args:
        left (list[float]): Left grayscale vector.
        right (list[float]): Right grayscale vector.

    Returns:
        float: Simplified SSIM score.

    Examples:
        >>> round(simple_ssim([1.0], [1.0]), 3)
        1.0
    """
    size = min(len(left), len(right))
    if size == 0:  # There is no structural-similarity evidence when either side is empty.
        return 0.0
    left = left[:size]
    right = right[:size]
    mean_left = sum(left) / size
    mean_right = sum(right) / size
    var_left = sum((value - mean_left) ** 2 for value in left) / size
    var_right = sum((value - mean_right) ** 2 for value in right) / size
    cov = sum((left[index] - mean_left) * (right[index] - mean_right) for index in range(size)) / size
    c1 = 0.01**2
    c2 = 0.03**2
    denominator = (mean_left**2 + mean_right**2 + c1) * (var_left + var_right + c2)
    if denominator <= 0:  # Guard against all-zero inputs or abnormal variance that invalidates the formula denominator.
        return 0.0
    return ((2 * mean_left * mean_right + c1) * (2 * cov + c2)) / denominator

def image_local_embedding(path: Path, dimensions: int = 128) -> list[float]:
    """Generate a local fallback embedding for an image.

    Business logic:
        1. Try reading a 16x16 grayscale vector.
        2. Fall back to a file-bytes hashing vector when the image cannot be read.
        3. Project grayscale bytes into a fixed-dimensional hash vector.

    Args:
        path (Path): Image file path.
        dimensions (int, optional): Output vector dimensionality. Defaults to 128.

    Returns:
        list[float]: Local image embedding vector.

    Examples:
        >>> image_local_embedding(Path("image.png"))  # doctest: +SKIP
        [0.0]
    """
    pixels = load_grayscale_vector(path, max_side=16)
    if not pixels:  # Use file-content hashing as the fallback feature when the image cannot be decoded.
        return bytes_hashing_vector(path.read_bytes(), dimensions=dimensions)
    chunks = []
    for value in pixels:  # Quantize grayscale values into bytes to reuse bytes_hashing_vector.
        chunks.append(int(value * 255).to_bytes(1, "big"))
    return bytes_hashing_vector(b"".join(chunks), dimensions=dimensions)

def average_hash(path: Path, hash_size: int = 8) -> int | None:
    """Compute the average hash for an image.

    Business logic:
        1. Prefer Pillow to convert to grayscale and resize to hash_size.
        2. Sample grayscale values with a P3 PPM fallback when Pillow fails.
        3. Set bits to 1 when pixel values are greater than or equal to the average grayscale value.

    Args:
        path (Path): Image file path.
        hash_size (int, optional): Hash side length. Defaults to 8.

    Returns:
        int | None: Average hash, or None when the image cannot be read.

    Examples:
        >>> average_hash(Path("image.png"))  # doctest: +SKIP
        0
    """
    try:
        from PIL import Image  # type: ignore

        with Image.open(path) as image:
            grayscale = image.convert("L").resize((hash_size, hash_size))
            values = list(grayscale.getdata())
    except Exception:
        ppm = read_ppm(path)
        if ppm is None:  # No usable pHash exists when neither Pillow nor PPM parsing can read the image.
            return None
        width, height, pixels = ppm
        values = []
        for y in range(hash_size):  # Sample each row of the target hash grid.
            src_y = min(height - 1, int(y * height / hash_size))
            for x in range(hash_size):  # Sample each column of the target hash grid.
                src_x = min(width - 1, int(x * width / hash_size))
                r, g, b = pixels[src_y * width + src_x]
                values.append(int(0.299 * r + 0.587 * g + 0.114 * b))

    average = sum(values) / max(len(values), 1)
    result = 0
    for index, value in enumerate(values):  # Each sampled grayscale value determines one hash bit.
        if value >= average:  # Pixels brighter than or equal to the average are set to 1 in the average hash.
            result |= 1 << index
    return result

def read_ppm(path: Path) -> tuple[int, int, list[tuple[int, int, int]]] | None:
    """Read an ASCII P3 PPM image.

    Business logic:
        1. Read ASCII text and remove comments.
        2. Validate the P3 header, dimensions, max value, and pixel count.
        3. Scale pixels into 0-255 RGB tuples.

    Args:
        path (Path): PPM file path.

    Returns:
        tuple[int, int, list[tuple[int, int, int]]] | None: Width, height, and pixel list, or None when parsing fails.

    Examples:
        >>> read_ppm(Path("image.ppm"))  # doctest: +SKIP
        (1, 1, [(0, 0, 0)])
    """
    try:
        text = path.read_text(encoding="ascii")
    except Exception:
        return None
    lines = []
    for line in text.splitlines():  # PPM comments start with # and must be removed first.
        line = line.split("#", 1)[0].strip()
        if line:  # Blank lines and pure-comment lines produce no tokens.
            lines.append(line)
    tokens = re.split(r"\s+", " ".join(lines))
    if len(tokens) < 4 or tokens[0] != "P3":  # Support only ASCII P3 PPM as a lightweight fallback.
        return None
    try:
        width = int(tokens[1])
        height = int(tokens[2])
        max_value = int(tokens[3])
        raw_values = [int(token) for token in tokens[4:]]
    except ValueError:
        return None
    if width <= 0 or height <= 0 or max_value <= 0:  # Image dimensions and max value must be positive.
        return None
    expected = width * height * 3
    if len(raw_values) < expected:  # Too few pixel values means the PPM file is incomplete.
        return None
    scale = 255 / max_value
    pixels = []
    for index in range(0, expected, 3):  # Every three values form one RGB pixel.
        pixels.append(
            (
                int(raw_values[index] * scale),
                int(raw_values[index + 1] * scale),
                int(raw_values[index + 2] * scale),
            )
        )
    return width, height, pixels

def fuse_image_edges(edges: list[dict[str, Any]], weights: dict[str, float]) -> list[dict[str, Any]]:
    """Fuse image duplicate candidate edges.

    Business logic:
        1. Merge candidate edges by undirected sample pair.
        2. Apply image_reason_weight to scores from different sources.
        3. Keep the highest score, all reasons, and the strongest duplicate_type.

    Args:
        edges (list[dict[str, Any]]): Candidate edges produced by upstream image operators.
        weights (dict[str, float]): Fusion weights for different image deduplication signals.

    Returns:
        list[dict[str, Any]]: Fused image duplicate edge list.

    Examples:
        >>> fuse_image_edges([], {})
        []
    """
    fused = {}
    for edge in edges:  # Aggregate every candidate edge by undirected pair.
        key = tuple(sorted([str(edge["left_id"]), str(edge["right_id"])]))
        reasons = edge.get("reasons", [edge.get("reason", "unknown")])
        score = float(edge.get("score", 0)) * image_reason_weight(reasons, weights)
        if key not in fused:  # Create a fused record immediately for a new pair.
            fused[key] = {
                "left_id": key[0],
                "right_id": key[1],
                "score": score,
                "duplicate_type": edge.get("duplicate_type", "near_duplicate"),
                "reasons": list(reasons),
                "operators": edge.get("operators", [edge.get("operator", "ImageDupFusionOperator")]),
            }
            continue
        fused_edge = fused[key]
        fused_edge["score"] = max(float(fused_edge["score"]), score)
        for reason in reasons:  # Preserve every image-duplicate evidence source for the same pair.
            if reason not in fused_edge["reasons"]:  # Do not write reasons that are already present.
                fused_edge["reasons"].append(reason)
        if edge.get("duplicate_type") == "exact_duplicate":  # exact_duplicate has the highest priority.
            fused_edge["duplicate_type"] = "exact_duplicate"
        elif edge.get("duplicate_type") == "semantic_duplicate" and fused_edge["duplicate_type"] != "exact_duplicate":
            fused_edge["duplicate_type"] = "semantic_duplicate"
    return list(fused.values())

def image_reason_weight(reasons: list[str], weights: dict[str, float]) -> float:
    """Choose a fusion weight from image duplicate reasons.

    Business logic:
        1. Traverse candidate-edge reasons.
        2. Match weights from keywords such as exact, phash, ssim, embedding, and object_region.
        3. Return the highest weight among all matched sources.

    Args:
        reasons (list[str]): Duplicate-reason list for a candidate edge.
        weights (dict[str, float]): Weight config for image deduplication signals.

    Returns:
        float: Fusion weight applied to the candidate edge.

    Examples:
        >>> image_reason_weight(["image_phash_hamming<=8"], {"phash": 0.9})
        1.0
    """
    score = 1.0
    for reason in reasons:  # Each reason may correspond to one image-deduplication signal.
        lower = reason.lower()
        if "exact" in lower:  # Exact signals such as file hashes use exact_hash weight.
            score = max(score, float(weights.get("exact_hash", 1.0)))
        elif "phash" in lower:
            score = max(score, float(weights.get("phash", 1.0)))
        elif "ssim" in lower:
            score = max(score, float(weights.get("ssim", 1.0)))
        elif "embedding" in lower:
            score = max(score, float(weights.get("embedding", 1.0)))
        elif "object_region" in lower:
            score = max(score, float(weights.get("object_region", 1.0)))
    return score
