from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class AudioFingerprintDeduplicator(BaseOperator):
    operator_name = "audio_fingerprint_deduplicator"  # Workflow config: near-duplicate audio-detection operator name based on energy-fingerprint string similarity.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect near-duplicate audio using energy fingerprints.

        Business logic:
            1. Generate one energy-spectrum fingerprint for each audio sample.
            2. Compute fingerprint-string similarity pairwise.
            3. Generate near_duplicate edges when the similarity reaches the threshold.

        Args:
            items (list[dict[str, Any]]): Sample list with normalized audio paths.
            context (dict[str, Any]): Shared workflow context.

        Returns:
            list[dict[str, Any]]: Sample list updated with audio_fingerprint.

        Examples:
            >>> AudioFingerprintDeduplicator({}).process_dataset([], {})
            []
        """
        threshold = float(self.config.get("similarity_threshold", 0.92))
        fingerprints: list[tuple[str, str]] = []
        for item in items:  # Try generating an energy fingerprint for every WAV sample.
            path_value = item.get("intermediate", {}).get("audio_path_abs")
            if not path_value:  # Skip samples missing a path.
                continue
            fingerprint = wav_energy_fingerprint(Path(path_value), bins=int(self.config.get("bins", 64)))
            if not fingerprint:  # Record an issue when the fingerprint cannot be generated.
                self.add_issue(item, "audio_fingerprint_failed")
                continue
            self.set_intermediate(item, "audio_fingerprint", fingerprint)
            fingerprints.append((str(item["id"]), fingerprint))

        for (left_id, left_fp), (right_id, right_fp) in combinations(fingerprints, 2):  # Fingerprint similarity requires pairwise comparison.
            score = string_similarity(left_fp, right_fp)
            if score >= threshold:  # Fingerprint pairs reaching the threshold become near-duplicate candidates.
                self.add_duplicate_edge(
                    context,
                    left_id,
                    right_id,
                    score,
                    f"audio_fingerprint>={threshold}",
                    "near_duplicate",
                )
        return items
