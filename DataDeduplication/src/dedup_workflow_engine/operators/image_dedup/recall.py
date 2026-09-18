from dedup_workflow_engine.utilities.image.shared import *  # noqa: F403

class ImageANNRecallOperator(BaseOperator):
    operator_name = "image_ann_recall"  # Workflow config: operator name for recalling semantic duplicate edges via cosine similarity on image embeddings.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Recall duplicate candidate edges from image embeddings.

        Business logic:
            1. Collect vectors from intermediate.image_embedding.
            2. Compute similar pairs by threshold and top_k.
            3. Write candidate pairs into duplicate_edges.

        Args:
            items (list[dict[str, Any]]): Image sample list that already contains image_embedding.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> ImageANNRecallOperator({}).process_dataset([], {})
            []
        """
        threshold = float(self.config.get("threshold", 0.9))
        top_k = int(self.config.get("top_k", 0))
        vectors = [
            (str(item["id"]), item.get("intermediate", {}).get("image_embedding", []))
            for item in items
            if item.get("intermediate", {}).get("image_embedding")
        ]
        for left_id, right_id, score in pairwise_topk(vectors, threshold=threshold, top_k=top_k):  # High-cosine-similarity pairs become image semantic duplicate candidates.
            self.add_duplicate_edge(
                context,
                left_id,
                right_id,
                score,
                f"image_embedding_cosine>={threshold}",
                "semantic_duplicate",
            )
        return items
