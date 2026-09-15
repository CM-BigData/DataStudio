from dedup_workflow_engine.utilities.audio.shared import *  # noqa: F403

class AudioNormalizeOperator(BaseOperator):
    operator_name = "audio_normalize"  # Workflow config: operator name for resolving audio paths and WAV metadata in the audio-dedup workflow.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize audio sample paths and collect WAV metadata.

        Business logic:
            1. Resolve the absolute path from payload.audio_path.
            2. Validate file existence and record file size.
            3. Try reading WAV sample rate, channel count, sample width, and duration.

        Args:
            items (list[dict[str, Any]]): Audio sample list.
            context (dict[str, Any]): Shared workflow context, expected to contain cwd.

        Returns:
            list[dict[str, Any]]: Sample list updated with audio_path_abs and audio metrics.

        Examples:
            >>> AudioNormalizeOperator({}).process_dataset([], {"cwd": "."})
            []
        """
        for item in items:  # Every audio sample must resolve its path first so downstream audio operators can reuse it.
            path = self.resolve_path(item, context, "audio_path")
            if path is None:  # Samples missing an audio path cannot enter the audio-dedup pipeline.
                self.add_issue(item, "missing_audio_path")
                item["action"] = "review"
                continue
            self.set_intermediate(item, "audio_path_abs", str(path))
            if not path.exists():  # Mark review instead of silently skipping when the file does not exist.
                self.add_issue(item, "audio_not_found")
                item["action"] = "review"
                continue
            self.set_metric(item, "file_size", path.stat().st_size)
            metadata = read_wav_metadata(path)
            if metadata:  # WAV metadata can support keep-quality scoring and delivery reporting.
                for key, value in metadata.items():  # Write each WAV metadata field into metrics.
                    self.set_metric(item, key, value)
            else:
                self.add_issue(item, "audio_decode_failed")
        return items
