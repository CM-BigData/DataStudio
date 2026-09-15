from dedup_workflow_engine.utilities.image.shared import *  # noqa: F403

class ImageFileHashDeduplicator(BaseOperator):
    operator_name = "image_file_hash_deduplicator"  # Workflow config: exact-duplicate detection operator name based on image-file SHA-256.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect completely identical files using image-file hashes.

        Business logic:
            1. Read image_path_abs from each sample.
            2. Compute SHA-256 for files that exist.
            3. Generate exact_duplicate edges for samples in the same hash bucket.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized image paths.
            context (dict[str, Any]): Shared workflow context used to append duplicate_edges.

        Returns:
            list[dict[str, Any]]: Sample list updated with image_file_hash.

        Examples:
            >>> ImageFileHashDeduplicator({}).process_dataset([], {})
            []
        """
        buckets: dict[str, list[str]] = {}
        for item in items:  # Every existing image file enters an exact-file-hash bucket.
            path_value = item.get("intermediate", {}).get("image_path_abs")
            if not path_value:  # Samples whose path normalization failed do not participate in file hashing.
                continue
            path = Path(path_value)
            if not path.exists():  # normalize has already marked missing files, so skip defensively here.
                continue
            digest = file_sha256(path)
            self.set_intermediate(item, "image_file_hash", digest)
            buckets.setdefault(digest, []).append(str(item["id"]))

        for member_ids in buckets.values():  # Only samples in the same file-hash bucket can be exact duplicate images.
            if len(member_ids) < 2:  # A single-sample bucket has no duplicate edge.
                continue
            first = member_ids[0]
            for other in member_ids[1:]:  # Use the first sample in the bucket as the representative for star-shaped duplicate edges.
                self.add_duplicate_edge(context, first, other, 1.0, "exact_image_file_hash", "exact_duplicate")
        return items

class ImagePHashDeduplicator(BaseOperator):
    operator_name = "image_phash_deduplicator"  # Workflow config: near-duplicate image-detection operator name based on average-hash Hamming distance.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect near-duplicate images using perceptual hashes.

        Business logic:
            1. Compute one average hash for each image.
            2. Record the hash and collect comparable fingerprints.
            3. Generate near_duplicate edges when Hamming distance stays below the threshold.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized image paths.
            context (dict[str, Any]): Shared workflow context used to append duplicate_edges.

        Returns:
            list[dict[str, Any]]: Sample list updated with image_phash.

        Examples:
            >>> ImagePHashDeduplicator({}).process_dataset([], {})
            []
        """
        hash_size = int(self.config.get("hash_size", 8))
        max_hamming_distance = int(self.config.get("max_hamming_distance", 8))
        hashes: list[tuple[str, int, int]] = []

        for item in items:  # Every decodable image produces a perceptual hash.
            path_value = item.get("intermediate", {}).get("image_path_abs")
            if not path_value:  # Skip samples missing a normalized path.
                continue
            value = average_hash(Path(path_value), hash_size=hash_size)
            if value is None:  # Mark an issue on decode failure so image samples are not dropped silently.
                self.add_issue(item, "image_phash_failed")
                continue
            self.set_intermediate(item, "image_phash", hex(value))
            hashes.append((str(item["id"]), value, hash_size * hash_size))

        for (left_id, left_hash, bits), (right_id, right_hash, _) in combinations(hashes, 2):  # pHash requires pairwise fingerprint-distance comparison.
            distance = bin(left_hash ^ right_hash).count("1")
            if distance <= max_hamming_distance:  # Small perceptual-hash distance means the images are visually close to duplicates.
                score = 1 - distance / bits
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"image_phash_hamming<={max_hamming_distance}",
                    "near_duplicate",
                )
        return items
