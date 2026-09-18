from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403

class MinHashLSHDeduplicator(BaseOperator):
    operator_name = "minhash_lsh_deduplicator"  # Workflow config: text near-duplicate recall operator name based on character-shingle Jaccard similarity.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect near-duplicate text using character-shingle Jaccard similarity.

        Business logic:
            1. Build shingle sets for normalized_text values that are long enough.
            2. Enumerate sample pairs and compute Jaccard scores.
            3. Append near_duplicate edges when the score reaches the threshold.

        Args:
            items (list[dict[str, Any]]): Sample list that has already completed text normalization.
            context (dict[str, Any]): Shared workflow context used to append duplicate_edges.

        Returns:
            list[dict[str, Any]]: Sample list updated with the text_shingle_count metric.

        Examples:
            >>> context = {}
            >>> MinHashLSHDeduplicator({"min_length": 1}).process_dataset([{"id": "a", "intermediate": {"normalized_text": "abcdef"}}], context)[0]["metrics"]["text_shingle_count"]
            2
        """
        threshold = float(self.config.get("jaccard_threshold", 0.8))
        shingle_size = int(self.config.get("shingle_size", 5))
        min_length = int(self.config.get("min_length", 40))
        sets: list[tuple[str, set[str]]] = []

        for item in items:  # Build shingle sets only for text long enough to compare.
            text = item.get("intermediate", {}).get("normalized_text", "")
            if len(text) < min_length:  # Jaccard scores on very short text are unstable, so skip it.
                continue
            shingles = make_shingles(text, shingle_size)
            self.set_metric(item, "text_shingle_count", len(shingles))
            if shingles:  # Empty shingle sets cannot participate in pairwise Jaccard.
                sets.append((str(item["id"]), shingles))

        for (left_id, left_set), (right_id, right_set) in combinations(sets, 2):  # Compute Jaccard for every comparable text set pair.
            union_count = len(left_set | right_set)
            if union_count == 0:  # Guard against division by zero from an empty union.
                continue
            score = len(left_set & right_set) / union_count
            if score >= threshold:  # Pairs meeting the threshold become text near-duplicate candidates.
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"minhash_jaccard>={threshold}",
                    "near_duplicate",
                )
        return items

def make_shingles(text: str, size: int) -> set[str]:
    """Convert text into a set of character shingles.

    Business logic:
        1. Remove all whitespace to create compact text.
        2. Return the whole string as a singleton set for short text.
        3. Generate size-length shingles with a character sliding window for longer text.

    Args:
        text (str): Normalized text.
        size (int): Shingle window size.

    Returns:
        set[str]: Character-shingle set.

    Examples:
        >>> make_shingles("abcd", 2)
        {'ab', 'bc', 'cd'}
    """
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= size:  # Keep the full text as a weak recall signal when it is shorter than one full window.
        return {compact} if compact else set()
    return {compact[index : index + size] for index in range(0, len(compact) - size + 1)}

def lexical_similarity(left: str, right: str) -> float:
    """Compute lightweight lexical Jaccard similarity between two texts.

    Business logic:
        1. Generate 3-character shingle sets for both texts.
        2. Return 0 when either side is empty.
        3. Return intersection size divided by union size.

    Args:
        left (str): Left text.
        right (str): Right text.

    Returns:
        float: Jaccard lexical-similarity score.

    Examples:
        >>> lexical_similarity("abcd", "abce") > 0
        True
    """
    left_set = make_shingles(left, 3)
    right_set = make_shingles(right, 3)
    if not left_set or not right_set:  # Without shingles on either side, there is no lexical-similarity evidence.
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)
