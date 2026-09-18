from dedup_workflow_engine.utilities.image.shared import *  # noqa: F403

class ImageDupFusionOperator(BaseOperator):
    operator_name = "image_dup_fusion"  # Workflow config: operator name for fusing multiple image duplicate candidate edges.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Fuse image duplicate candidate edges.

        Business logic:
            1. Read weights for exact_hash, phash, ssim, embedding, and object_region.
            2. Call fuse_image_edges to merge candidate edges for the same pair.
            3. Replace context.duplicate_edges with the fused result.

        Args:
            items (list[dict[str, Any]]): Image sample list.
            context (dict[str, Any]): Shared workflow context containing duplicate_edges.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> context = {"duplicate_edges": []}
            >>> ImageDupFusionOperator({}).process_dataset([], context)
            []
        """
        weights = self.config.get(
            "weights",
            {
                "exact_hash": 1.0,
                "phash": 0.9,
                "ssim": 0.85,
                "embedding": 0.9,
                "object_region": 0.95,
            },
        )
        context["duplicate_edges"] = fuse_image_edges(context.get("duplicate_edges", []), weights)
        return items
