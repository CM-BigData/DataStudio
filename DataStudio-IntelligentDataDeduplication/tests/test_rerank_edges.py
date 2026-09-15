import unittest

from dedup_workflow_engine.operators.text_dedup.rerank import _unique_edges_by_pair


class RerankEdgesTest(unittest.TestCase):
    def test_unique_edges_by_pair_merges_reasons_and_keeps_best_score(self) -> None:
        """Verify that duplicate-edge deduplication merges reasons and keeps the best score.

        Business logic:
            1. Build two candidate duplicate edges with opposite directions but the same sample pair.
            2. Call _unique_edges_by_pair to normalize and merge them.
            3. Assert that only one a-b edge remains with the best score and all reasons.

        Args:
            None: unittest creates the test instance automatically.

        Returns:
            None: Test results are expressed through assertions.

        Examples:
            >>> RerankEdgesTest().test_unique_edges_by_pair_merges_reasons_and_keeps_best_score()  # doctest: +SKIP
        """
        edges = [
            {
                "left_id": "b",
                "right_id": "a",
                "score": 0.8,
                "reason": "simhash_hamming<=10",
                "duplicate_type": "near_duplicate",
                "operator": 'simhash_deduplicator',
            },
            {
                "left_id": "a",
                "right_id": "b",
                "score": 1.0,
                "reason": "exact_text_hash",
                "duplicate_type": "exact_duplicate",
                "operator": 'exact_hash_deduplicator',
            },
        ]

        unique = _unique_edges_by_pair(edges)

        self.assertEqual(len(unique), 1)
        self.assertEqual(unique[0]["left_id"], "a")
        self.assertEqual(unique[0]["right_id"], "b")
        self.assertEqual(unique[0]["score"], 1.0)
        self.assertIn("simhash_hamming<=10", unique[0]["reasons"])
        self.assertIn("exact_text_hash", unique[0]["reasons"])


if __name__ == "__main__":
    unittest.main()
