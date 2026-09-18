from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403

class VideoProbeOperator(VideoOperator):
    operator_name: str = "video_probe"  # Operator identifier used by workflow configs and the registry.

    SUPPORTED_EXTENSIONS: set[str] = {".mp4", ".mov", ".avi", ".mkv", ".webm"}  # Supported file extensions accepted during video probing.

    def process(self, item: dict) -> dict:
        """Probe container metadata and streams for one video sample.

        Business logic:
            1. Validate file existence, size, and extension.
            2. Run ffprobe and extract video/audio stream metadata.
            3. Record duration, size, frame rate, and stream-related issues.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out video processing.
            return item
        path = self.video_path(item)
        if not path.exists():  # Record a missing-file issue when the video path does not exist.
            self.add_issue(item, "video_missing")
            self.set_metric(item, "video_readable", False)
            return item
        self.set_metric(item, "video_readable", True)
        self.set_metric(item, "video_bytes", path.stat().st_size)
        if path.suffix.lower() not in self.SUPPORTED_EXTENSIONS:  # Flag unsupported container extensions.
            self.add_issue(item, "unsupported_video_format")
        if path.stat().st_size < int(self.config.get("min_bytes", 1024)):  # Flag videos that are too small to be meaningful.
            self.add_issue(item, "video_too_small")

        probe = self._probe(path)
        if probe is None:  # Record failure when ffprobe cannot return metadata.
            self.add_issue(item, "ffprobe_failed")
            return item

        item.setdefault("intermediate", {})["ffprobe"] = probe
        streams = probe.get("streams", [])
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        if not video_stream:  # Flag containers that do not contain a video stream.
            self.add_issue(item, "no_video_stream")
            return item

        duration = float(probe.get("format", {}).get("duration") or video_stream.get("duration") or 0)
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
        fps = parse_fps(video_stream.get("avg_frame_rate") or video_stream.get("r_frame_rate") or "0/1")
        self.set_metric(item, "duration_seconds", round(duration, 4))
        self.set_metric(item, "width", width)
        self.set_metric(item, "height", height)
        self.set_metric(item, "fps", round(fps, 4))
        self.set_metric(item, "has_audio", audio_stream is not None)

        if duration and duration < float(self.config.get("min_duration", 1.0)):  # Flag videos shorter than the configured minimum.
            self.add_issue(item, "video_too_short")
        if duration > float(self.config.get("max_duration", 3600.0)):  # Flag videos longer than the configured maximum.
            self.add_issue(item, "video_too_long")
        if width < int(self.config.get("min_width", 160)) or height < int(self.config.get("min_height", 120)):  # Flag low-resolution videos under the configured threshold.
            self.add_issue(item, "low_video_resolution")
        if fps and fps < float(self.config.get("min_fps", 10.0)):  # Flag low frame rates under the configured threshold.
            self.add_issue(item, "low_fps")
        return item

    def _probe(self, path: Path) -> dict | None:
        """Call ffprobe and parse its JSON output.

        Business logic:
            1. Build the ffprobe command with JSON output enabled.
            2. Execute the command with a timeout.
            3. Return parsed JSON output or `None` on failure.

        Args:
                path (Path): File path.

        Returns:
            dict | None: Parsed ffprobe result, or `None` on failure.

        Examples:
            >>> _probe
            _probe
        """
        cmd = [
            ffprobe_path(),
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
            if completed.returncode != 0:  # Return failure when the subprocess exits unsuccessfully.
                return None
            return json.loads(completed.stdout)
        except Exception:
            return None

class VideoDecodeCheckOperator(VideoOperator):
    operator_name: str = "video_decode_check"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Verify that one video sample can be decoded end to end.

        Business logic:
            1. Run ffmpeg decode validation over the full video.
            2. Record whether the decode check passed.
            3. Store a decode-failure issue and truncated stderr when decoding fails.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or "video_missing" in item.get("issues", []):  # Skip decode checks when the file is missing or earlier workflow state blocks processing.
            return item
        cmd = [ffmpeg_path(), "-v", "error", "-i", str(self.video_path(item)), "-f", "null", "-"]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=int(self.config.get("timeout", 60)))
            self.set_metric(item, "decode_check_passed", completed.returncode == 0)
            if completed.returncode != 0:  # Flag decode failure when the subprocess exits unsuccessfully.
                self.add_issue(item, "decode_failed")
                item.setdefault("intermediate", {})["decode_error"] = completed.stderr[-500:]
        except Exception as exc:
            self.add_issue(item, "decode_failed")
            item.setdefault("intermediate", {})["decode_error"] = str(exc)
        return item
