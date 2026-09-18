from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403

class SimHashDeduplicator(BaseOperator):
    operator_name = "simhash_deduplicator"  # Workflow config: near-duplicate text recall operator name based on SimHash Hamming distance.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect near-duplicate text using SimHash fingerprints.

        Business logic:
            1. Compute one SimHash fingerprint for each normalized_text.
            2. Enumerate fingerprint pairs and compute Hamming distance.
            3. Generate near_duplicate edges when the distance stays within the threshold.

        Args:
            items (list[dict[str, Any]]): Normalized text sample list.
            context (dict[str, Any]): Shared workflow context used to append duplicate_edges.

        Returns:
            list[dict[str, Any]]: Sample list updated with SimHash intermediate results.

        Examples:
            >>> context = {}
            >>> SimHashDeduplicator({}).process_dataset([{"id": "a", "intermediate": {"normalized_text": "hello"}}], context)[0]["intermediate"].get("simhash") is not None
            True
        """
        bit_size = int(self.config.get("bit_size", 64))
        max_hamming_distance = int(self.config.get("max_hamming_distance", 3))
        ngram = int(self.config.get("ngram", 2))
        vectors: list[tuple[str, int]] = []

        for item in items:  # Every non-empty normalized_text produces one comparable fingerprint.
            text = item.get("intermediate", {}).get("normalized_text", "")
            if not text:  # Empty text cannot form stable SimHash evidence.
                continue
            fingerprint = simhash(text, bit_size=bit_size, ngram=ngram)
            self.set_intermediate(item, "simhash", fingerprint)
            vectors.append((str(item["id"]), fingerprint))

        for (left_id, left_hash), (right_id, right_hash) in combinations(vectors, 2):  # SimHash requires pairwise fingerprint-distance comparison.
            distance = hamming_distance(left_hash, right_hash)
            if distance <= max_hamming_distance:  # Smaller distance means closer duplication; generate a candidate edge within the threshold.
                score = 1 - distance / bit_size
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"simhash_hamming<={max_hamming_distance}",
                    "near_duplicate",
                )
        return items

def tokenize_for_simhash(text: str, ngram: int) -> list[str]:
    """Generate compact character-ngram tokens for SimHash.

    Business logic:
        1. Remove all whitespace from the text.
        2. Return the whole text when its length does not exceed ngram.
        3. Generate ngram tokens with a sliding window for longer text.

    Args:
        text (str): Normalized text.
        ngram (int): Character-ngram window size.

    Returns:
        list[str]: Token list used by SimHash.

    Examples:
        >>> tokenize_for_simhash("abcd", 2)
        ['ab', 'bc', 'cd']
    """
    compact = re.sub(r"\s+", "", text)
    if len(compact) <= ngram:  # Keep the full text as the only token when short text cannot slide a window.
        return [compact] if compact else []
    return [compact[index : index + ngram] for index in range(0, len(compact) - ngram + 1)]

def simhash(text: str, bit_size: int = 64, ngram: int = 2) -> int:
    """Compute the SimHash fingerprint for text.

    Business logic:
        1. Split the text into ngram tokens.
        2. Update per-bit weights using each token's blake2b digest.
        3. Set bits whose final weight is greater than 0 to form the final integer fingerprint.

    Args:
        text (str): Normalized text.
        bit_size (int, optional): Number of SimHash bits. Defaults to 64.
        ngram (int, optional): Token ngram size. Defaults to 2.

    Returns:
        int: Integer SimHash fingerprint.

    Examples:
        >>> isinstance(simhash("hello"), int)
        True
    """
    weights = [0] * bit_size
    for token in tokenize_for_simhash(text, ngram):  # Each token votes across all bit dimensions.
        digest = int(hashlib.blake2b(token.encode("utf-8"), digest_size=8).hexdigest(), 16)
        for bit in range(bit_size):  # Increase or decrease the weight for the bit indicated by the digest.
            if digest & (1 << bit):  # Cast a positive vote when the token digest has a 1 in this bit.
                weights[bit] += 1
            else:
                weights[bit] -= 1
    result = 0
    for bit, weight in enumerate(weights):  # Aggregate all token votes into the final fingerprint.
        if weight > 0:  # Positive weight means most tokens lean toward 1 for that bit.
            result |= 1 << bit
    return result

def hamming_distance(left: int, right: int) -> int:
    """Compute the Hamming distance between two SimHash fingerprints.

    Business logic:
        1. XOR the two integer fingerprints.
        2. Count bits set to 1 in the XOR result.
        3. Return the number of differing bits as the near-duplicate distance.

    Args:
        left (int): Left SimHash fingerprint.
        right (int): Right SimHash fingerprint.

    Returns:
        int: Number of differing bits between the two fingerprints.

    Examples:
        >>> hamming_distance(0b1010, 0b1001)
        2
    """
    return bin(left ^ right).count("1")
