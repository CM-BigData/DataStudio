from typing import Any
from denoise_workflow_engine.utilities.video.base import *  # noqa: F403
from denoise_workflow_engine.runtime.loader import safe_child_path

class VideoRepairOperator(VideoOperator):
    operator_name: str = "video_repair"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Repair recoverable quality issues in one video sample.

        Business logic:
            1. Skip repair for missing, undecodable, or hard-fail videos.
            2. Apply deterministic ffmpeg-based fixes for audio volume and exposure issues.
            3. Save the repaired video and update payload, intermediate paths, and repair metrics.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or has_any_issue(
            item,
            {"video_missing", "decode_failed", "no_video_stream", "ffprobe_failed", "black_frames", "freeze_frames"},
        ):
            self.set_metric(item, "video_repair_applied", False)
            return item
        issues = set(item.get("issues", []))
        repairable = set(self.config.get("repair_issues", ["low_audio_volume", "video_under_exposure", "video_over_exposure"]))
        if not (issues & repairable):  # Preserve the original video path when no repair-trigger issue is present.
            self.set_metric(item, "video_repair_applied", False)
            return item
        configured_output = self.config.get("output_dir")
        output_dir = (
            self.resolve_runtime_path(str(configured_output), name="video repair output directory")
            if configured_output
            else safe_child_path(self.runtime_run_dir(), "repaired_videos", "video repair output directory")
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        src = self.video_path(item)
        target = safe_child_path(
            output_dir,
            f"{self.safe_item_id(item, src.stem)}_repaired.mp4",
            "repaired video path",
        )
        filters = []
        if "low_audio_volume" in issues:  # Add a volume boost filter when low-audio-volume issues are present.
            filters.extend(["-af", f"volume={float(self.config.get('audio_volume_factor', 3.0))}"])
        if "video_under_exposure" in issues:  # Apply a brightness boost for under-exposed videos.
            filters.extend(["-vf", f"eq=brightness={float(self.config.get('brightness_boost', 0.08))}"])
        elif "video_over_exposure" in issues:
            filters.extend(["-vf", f"eq=brightness={float(self.config.get('brightness_reduce', -0.08))}"])
        cmd = [ffmpeg_path(), "-y", "-i", str(src), *filters, "-c:v", "mpeg4", "-c:a", "aac", str(target)]
        try:
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=int(self.config.get("timeout", 90)))
            if completed.returncode == 0 and target.exists():  # Switch the sample path only when ffmpeg succeeds and the output exists.
                item.setdefault("intermediate", {})["video_before_repair"] = str(src)
                item["intermediate"]["video_after_repair"] = str(target)
                item.setdefault("payload", {})["original_video_path"] = str(src).replace("\\", "/")
                item["payload"]["video_path"] = rel_to_root(target)
                item["issues"] = [issue for issue in item.get("issues", []) if issue not in repairable]
                self.add_issue(item, "video_repaired")
                self.set_metric(item, "video_repair_applied", True)
                self.set_metric(item, "video_repair_output", rel_to_root(target))
            else:
                self.add_issue(item, "video_repair_failed")
                self.set_metric(item, "video_repair_applied", False)
                self.set_metric(item, "video_repair_error", completed.stderr[-500:])
        except Exception as exc:
            self.add_issue(item, "video_repair_failed")
            self.set_metric(item, "video_repair_applied", False)
            self.set_metric(item, "video_repair_error", str(exc))
        return item
