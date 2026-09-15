from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403

class ExactHashDeduplicator(BaseOperator):
    operator_name = "exact_hash_deduplicator"  # Workflow config: exact-text deduplication operator name based on SHA-256 of normalized_text.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect exact duplicate samples using normalized-text hashes.

        Business logic:
            1. Read intermediate.normalized_text from each sample.
            2. Compute SHA-256 for non-empty text and bucket samples by digest.
            3. Generate exact_duplicate edges for samples inside the same bucket.

        Args:
            items (list[dict[str, Any]]): Sample list that has already completed text normalization.
            context (dict[str, Any]): Shared workflow context used to append duplicate_edges.

        Returns:
            list[dict[str, Any]]: Original sample list updated with text_exact_hash.

        Examples:
            >>> items = [{"id": "a", "intermediate": {"normalized_text": "x"}}, {"id": "b", "intermediate": {"normalized_text": "x"}}]
            >>> context = {}
            >>> ExactHashDeduplicator({}).process_dataset(items, context)
            [{'id': 'a', 'intermediate': {'normalized_text': 'x', 'text_exact_hash': '2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881'}}, {'id': 'b', 'intermediate': {'normalized_text': 'x', 'text_exact_hash': '2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881'}}]
        """
        buckets: dict[str, list[str]] = {}
        for item in items:  # Every usable normalized_text enters an exact-hash bucket.
            normalized = item.get("intermediate", {}).get("normalized_text")
            if not normalized:  # Empty text is already marked by the normalize operator and does not participate in exact-duplicate checks.
                continue
            digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            self.set_intermediate(item, "text_exact_hash", digest)
            buckets.setdefault(digest, []).append(str(item["id"]))

        for member_ids in buckets.values():  # Only samples in the same digest bucket can be exact duplicate text.
            if len(member_ids) < 2:  # A single-sample bucket has no duplicate edge to generate.
                continue
            first = member_ids[0]
            for other in member_ids[1:]:  # Use the first sample in the bucket as the representative when generating star-shaped edges.
                self.add_duplicate_edge(context, first, other, 1.0, "exact_text_hash", "exact_duplicate")
        return items
