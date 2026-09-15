from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403

class AudioExtractOperator(VideoOperator):
    operator_name: str = "audio_extract"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Extract a mono WAV track from one video sample.

        Business logic:
            1. Skip samples whose video is missing or known to have no audio.
            2. Invoke ffmpeg to extract a normalized mono 16kHz audio track.
            3. Record extraction metrics or failure issues.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or "video_missing" in item.get("issues", []):  # Skip audio extraction when the video is missing or earlier workflow state blocks processing.
            return item
        if item.get("metrics", {}).get("has_audio") is False:  # Skip extraction when probing already confirmed there is no audio track.
            self.add_issue(item, "audio_missing")
            return item
        out_dir = self.run_dir(item, "audio")
        audio_path = out_dir / "audio.wav"
        cmd = [
            ffmpeg_path(),
            "-y",
            "-i",
            str(self.video_path(item)),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(audio_path),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=int(self.config.get("timeout", 60)))
        if completed.returncode != 0 or not audio_path.exists():  # Mark extraction failure when ffmpeg does not produce the audio file.
            self.add_issue(item, "audio_extract_failed")
            return item
        item.setdefault("intermediate", {})["audio_path"] = str(audio_path)
        self.set_metric(item, "audio_bytes", audio_path.stat().st_size)
        return item

class AudioQualityOperator(VideoOperator):
    operator_name: str = "audio_quality"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Evaluate basic loudness quality for one video sample.

        Business logic:
            1. Run ffmpeg volumedetect over the video audio stream.
            2. Parse mean and max loudness metrics.
            3. Add issues for silent or abnormally quiet audio.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or "audio_missing" in item.get("issues", []):  # Skip loudness analysis when the sample has no audio track.
            return item
        cmd = [
            ffmpeg_path(),
            "-i",
            str(self.video_path(item)),
            "-af",
            "volumedetect",
            "-vn",
            "-sn",
            "-dn",
            "-f",
            "null",
            "-",
        ]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=int(self.config.get("timeout", 60)))
            output = completed.stderr
            mean_volume = parse_volume(output, "mean_volume")
            max_volume = parse_volume(output, "max_volume")
            if mean_volume is not None:  # Record average loudness when parsing succeeds.
                self.set_metric(item, "audio_mean_volume_db", mean_volume)
            if max_volume is not None:  # Record peak loudness when parsing succeeds.
                self.set_metric(item, "audio_max_volume_db", max_volume)
            if max_volume is not None and max_volume < float(self.config.get("silent_max_volume_db", -50.0)):  # Flag silent audio when peak volume is below the configured threshold.
                self.add_issue(item, "silent_audio")
            elif mean_volume is not None and mean_volume < float(self.config.get("low_mean_volume_db", -38.0)):
                self.add_issue(item, "low_audio_volume")
        except Exception:
            self.add_issue(item, "audio_quality_failed")
        return item
