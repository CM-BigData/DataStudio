from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class AudioDupFusionOperator(BaseOperator):
    operator_name = "audio_dup_fusion"  # Workflow config: operator name for fusing multiple audio duplicate candidate edges.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Fuse audio duplicate candidate edges.

        Business logic:
            1. Read weights for exact_hash, fingerprint, acoustic, embedding, asr, and pcm.
            2. Call fuse_audio_edges to merge candidate edges for the same pair.
            3. Replace context.duplicate_edges with the fused result.

        Args:
            items (list[dict[str, Any]]): Audio sample list.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> context = {"duplicate_edges": []}
            >>> AudioDupFusionOperator({}).process_dataset([], context)
            []
        """
        weights = self.config.get(
            "weights",
            {
                "exact_hash": 1.0,
                "fingerprint": 0.95,
                "acoustic": 0.85,
                "embedding": 0.9,
                "asr": 0.9,
                "pcm": 1.0,
            },
        )
        context["duplicate_edges"] = fuse_audio_edges(context.get("duplicate_edges", []), weights)
        return items
