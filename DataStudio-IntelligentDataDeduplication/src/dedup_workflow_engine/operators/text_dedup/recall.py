from dedup_workflow_engine.utilities.text.shared import *  # noqa: F403

class ANNRecallOperator(BaseOperator):
    operator_name = "ann_recall"  # Workflow config: operator name for recalling semantic duplicate edges via cosine similarity on text embeddings.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate semantic duplicate candidate edges from text embeddings.

        Business logic:
            1. Collect vectors from intermediate.text_embedding.
            2. Use pairwise_topk to recall similar pairs by threshold and top_k.
            3. Write recalled pairs into context.duplicate_edges.

        Args:
            items (list[dict[str, Any]]): Sample list that already contains text_embedding.
            context (dict[str, Any]): Shared workflow context used to append duplicate_edges.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> context = {}
            >>> ANNRecallOperator({"threshold": 0.9}).process_dataset([], context)
            []
        """
        threshold = float(self.config.get("threshold", 0.82))
        top_k = int(self.config.get("top_k", 0))
        vectors = [
            (str(item["id"]), item.get("intermediate", {}).get("text_embedding", []))
            for item in items
            if item.get("intermediate", {}).get("text_embedding")
        ]
        for left_id, right_id, score in pairwise_topk(vectors, threshold=threshold, top_k=top_k):  # Each highly similar pair becomes a semantic duplicate candidate edge.
            self.add_duplicate_edge(
                context,
                left_id,
                right_id,
                score,
                f"text_embedding_cosine>={threshold}",
                "semantic_duplicate",
            )
        return items
