from __future__ import annotations

import hashlib

from synthesis_engine.models import GenerationItem


def compute_diversity_score(signature: str, seen_hashes: set[str]) -> tuple[float, bool]:
    """Compute the diversity score from a sample signature.

    Business logic:
        1. Hash the normalized signature text.
        2. Treat repeated hashes as duplicates.
        3. Return the score together with the duplicate flag.

    Args:
        signature (str): Normalized sample signature.
        seen_hashes (set[str]): Process-local signature hashes.

    Returns:
        tuple[float, bool]: Diversity score and duplicate flag.

    Examples:
        >>> compute_diversity_score("x", set())[0]
        1.0
    """
    digest = hashlib.sha256(signature.encode("utf-8")).hexdigest()

    if digest in seen_hashes:  # Repeated signature hashes represent duplicate generations.

        return 0.0, True

    seen_hashes.add(digest)

    return 1.0, False


def _signature(item: GenerationItem) -> str:
    """Extract a deduplication signature for the sample.

    Business logic:
        1. Read the core generated fields by task type.
        2. Use sorted record items for structured results.
        3. Fall back to whitespace-compressed generated content for unknown types.

    Args:
        item (GenerationItem): Sample whose signature should be extracted.

    Returns:
        str: Signature text used for diversity checks.

    Examples:
        >>> _signature(GenerationItem('a', 'text', 'p', generated={'text': 'x'}))
        'x'
    """

    if item.task_type == "text":  # Use generated text directly for text tasks.

        return item.generated.get("text", "")

    if item.task_type == "image":  # Combine image path and prompt to reduce collisions for image tasks.

        return item.generated.get("image_path", "") + item.prompt

    if item.task_type == "structured":  # Sort record items so structured signatures stay stable.

        return str(sorted(item.generated.get("record", {}).items()))

    return " ".join(str(item.generated).split())


__all__ = ["_signature", "compute_diversity_score"]
