from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class AudioFileHashDeduplicator(BaseOperator):
    operator_name = "audio_file_hash_deduplicator"  # Workflow config: exact-duplicate detection operator name based on audio-file SHA-256.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect completely identical files using audio-file hashes.

        Business logic:
            1. Read audio_path_abs from each sample.
            2. Compute SHA-256 for existing files and bucket them.
            3. Generate exact_duplicate edges for samples in the same hash bucket.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized audio paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with audio_file_hash.

        Examples:
            >>> AudioFileHashDeduplicator({}).process_dataset([], {})
            []
        """
        buckets: dict[str, list[str]] = {}
        for item in items:  # Every existing audio file enters an exact-file-hash bucket.
            path_value = item.get("intermediate", {}).get("audio_path_abs")
            if not path_value:  # Samples whose path normalization failed do not participate in file hashing.
                continue
            path = Path(path_value)
            if not path.exists():  # normalize has already marked missing files, so skip defensively here.
                continue
            digest = file_sha256(path)
            self.set_intermediate(item, "audio_file_hash", digest)
            buckets.setdefault(digest, []).append(str(item["id"]))

        for member_ids in buckets.values():  # Only samples in the same file-hash bucket can be exact duplicate audio.
            if len(member_ids) < 2:  # A single-sample bucket has no duplicate edge.
                continue
            first = member_ids[0]
            for other in member_ids[1:]:  # Use the first sample in the bucket as the representative for star-shaped duplicate edges.
                self.add_duplicate_edge(context, first, other, 1.0, "exact_audio_file_hash", "exact_duplicate")
        return items

class AudioPCMHashDeduplicator(BaseOperator):
    operator_name = "audio_pcm_hash_deduplicator"  # Workflow config: normalized-audio duplicate-detection operator name based on WAV PCM content hashes.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect audio duplicates using WAV PCM-content hashes.

        Business logic:
            1. Read audio_path_abs from each sample.
            2. Compute a hash including channels, sample width, sample rate, and PCM frames.
            3. Generate exact_duplicate edges for samples in the same PCM-hash bucket.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized audio paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with audio_pcm_hash.

        Examples:
            >>> AudioPCMHashDeduplicator({}).process_dataset([], {})
            []
        """
        buckets: dict[str, list[str]] = {}
        for item in items:  # Try computing a normalized PCM hash for every WAV sample.
            path_value = item.get("intermediate", {}).get("audio_path_abs")
            if not path_value:  # Skip samples missing a path.
                continue
            digest = wav_pcm_sha256(Path(path_value))
            if digest is None:  # Record PCM-hash failure for non-WAV files or read failures.
                self.add_issue(item, "audio_pcm_hash_failed")
                continue
            self.set_intermediate(item, "audio_pcm_hash", digest)
            buckets.setdefault(digest, []).append(str(item["id"]))

        for member_ids in buckets.values():  # The same PCM-hash bucket means audio content is identical.
            if len(member_ids) < 2:  # A single-sample bucket has no duplicate edge.
                continue
            first = member_ids[0]
            for other in member_ids[1:]:  # Use the first sample in the bucket as the representative when generating duplicate edges.
                self.add_duplicate_edge(context, first, other, 1.0, "normalized_audio_pcm_hash", "exact_duplicate")
        return items
