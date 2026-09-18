from dedup_workflow_engine.utilities.image.shared import *  # noqa: F403

class ImageSSIMOperator(BaseOperator):
    operator_name = "image_ssim"  # Workflow config: near-duplicate image-detection operator name based on grayscale structural similarity.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect near-duplicate images using grayscale SSIM scores.

        Business logic:
            1. Generate a fixed-side-length grayscale vector for each image.
            2. Compute simple_ssim scores pairwise.
            3. Append near_duplicate edges when the score reaches the threshold.

        Args:
            items (list[dict[str, Any]]): Image sample list with normalized paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with image_ssim_vector.

        Examples:
            >>> ImageSSIMOperator({}).process_dataset([], {})
            []
        """
        threshold = float(self.config.get("threshold", 0.92))
        max_side = int(self.config.get("max_side", 64))
        images: list[tuple[str, list[float]]] = []
        for item in items:  # Every decodable image produces an SSIM comparison vector.
            path_value = item.get("intermediate", {}).get("image_path_abs")
            if not path_value:  # Skip samples missing a path.
                continue
            pixels = load_grayscale_vector(Path(path_value), max_side=max_side)
            if not pixels:  # Record an issue when the image cannot be decoded into a grayscale vector.
                self.add_issue(item, "image_ssim_load_failed")
                continue
            self.set_intermediate(item, "image_ssim_vector", pixels)
            images.append((str(item["id"]), pixels))

        for (left_id, left_pixels), (right_id, right_pixels) in combinations(images, 2):  # SSIM requires pairwise comparison of image vectors.
            score = simple_ssim(left_pixels, right_pixels)
            if score >= threshold:  # Generate near-duplicate edges when structural similarity reaches the threshold.
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"image_ssim>={threshold}",
                    "near_duplicate",
                )
        return items

class ObjectRegionSimilarityOperator(BaseOperator):
    operator_name = "object_region_similarity"  # Workflow config: semantic image-duplicate detection operator name based on object-region embeddings.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect semantic image duplicates using object-region embeddings.

        Business logic:
            1. Return immediately when the feature is not enabled in config.
            2. Prefer payload.object_region_embedding and fall back to image_embedding when it is missing.
            3. Generate semantic_duplicate edges by cosine-similarity threshold.

        Args:
            items (list[dict[str, Any]]): Image sample list.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Original sample list.

        Examples:
            >>> ObjectRegionSimilarityOperator({"enabled": False}).process_dataset([], {})
            []
        """
        if not config_enabled(self.config):  # Object-region modeling is optional and should not change samples when disabled.
            return items
        threshold = float(self.config.get("threshold", 0.9))
        vectors = []
        for item in items:  # Each sample tries to read an object-region embedding or fall back to the full-image embedding.
            region_embedding = item.get("payload", {}).get("object_region_embedding") or item.get("intermediate", {}).get(
                "image_embedding"
            )
            if not region_embedding:  # Semantic recall cannot run when no region embedding is available.
                self.add_issue(item, "object_region_model_not_configured")
                continue
            vectors.append((str(item["id"]), region_embedding))
        for left_id, right_id, score in pairwise_topk(vectors, threshold=threshold, top_k=int(self.config.get("top_k", 0))):  # Highly similar region vectors form semantic duplicate edges.
            self.add_duplicate_edge(
                context,
                left_id,
                right_id,
                score,
                f"object_region_similarity>={threshold}",
                "semantic_duplicate",
            )
        return items
