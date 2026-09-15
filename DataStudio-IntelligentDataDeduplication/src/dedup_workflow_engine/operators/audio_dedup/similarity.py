from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class MFCCSimilarityOperator(BaseOperator):
    operator_name = "mfcc_similarity"  # Workflow config: near-duplicate audio-detection operator name based on cosine similarity of acoustic feature vectors.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Recall near-duplicate audio using acoustic vectors.

        Business logic:
            1. Generate one acoustic feature vector for each audio sample.
            2. Compute vector-pair similarity by threshold and top_k.
            3. Write high-similarity pairs as near_duplicate edges.

        Args:
            items (list[dict[str, Any]]): Audio sample list with normalized paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with audio_acoustic_vector.

        Examples:
            >>> MFCCSimilarityOperator({}).process_dataset([], {})
            []
        """
        threshold = float(self.config.get("similarity_threshold", 0.92))
        vectors: list[tuple[str, list[float]]] = []
        for item in items:  # Try generating an acoustic feature vector for every audio file.
            path_value = item.get("intermediate", {}).get("audio_path_abs")
            if not path_value:  # Skip samples missing a path.
                continue
            vector = wav_acoustic_vector(Path(path_value), bins=int(self.config.get("bins", 64)))
            if not vector:  # Record an issue when acoustic feature extraction fails.
                self.add_issue(item, "audio_mfcc_fallback_failed")
                continue
            self.set_intermediate(item, "audio_acoustic_vector", vector)
            vectors.append((str(item["id"]), vector))
        for left_id, right_id, score in pairwise_topk(vectors, threshold=threshold, top_k=int(self.config.get("top_k", 0))):  # Highly similar acoustic vectors form near-duplicate candidate edges.
            self.add_duplicate_edge(
                context,
                left_id,
                right_id,
                score,
                f"audio_acoustic_cosine>={threshold}",
                "near_duplicate",
            )
        return items
