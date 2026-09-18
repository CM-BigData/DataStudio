from typing import Any
from denoise_workflow_engine.utilities.image.base import *  # noqa: F403

class ImageMetaOperator(ImageOperator):
    operator_name: str = "image_meta"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Extract size and aspect-ratio metadata from one image sample.

        Business logic:
            1. Skip images that are unreadable or missing.
            2. Read width, height, and aspect ratio through Pillow.
            3. Add issues for low resolution or abnormal aspect ratio.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or "decode_failed" in item.get("issues", []) or "image_missing" in item.get("issues", []):  # Skip metadata extraction when the image is unreadable or missing.
            return item
        if Image is None:  # Metadata extraction is unavailable without Pillow.
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                width, height = image.size
                self.set_metric(item, "width", width)
                self.set_metric(item, "height", height)
                self.set_metric(item, "aspect_ratio", round(width / max(height, 1), 4))
                if width < int(self.config.get("min_width", 128)) or height < int(self.config.get("min_height", 128)):  # Flag low-resolution images under the configured size threshold.
                    self.add_issue(item, "low_resolution")
                ratio = width / max(height, 1)
                if ratio < float(self.config.get("min_aspect_ratio", 0.2)) or ratio > float(
                    self.config.get("max_aspect_ratio", 5.0)
                ):
                    self.add_issue(item, "abnormal_aspect_ratio")
        except Exception:
            self.add_issue(item, "decode_failed")
        return item
