from __future__ import annotations

from pathlib import Path

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class ImageQualityInspectOperator(BaseOperator):
    operator_name = "image_quality_inspect"  # Operator name: registry name for the basic image quality inspection step.

    def process(self, item: DataItem) -> DataItem:
        """Inspect basic image size and mode information.

        Business logic:
            1. Pass non-image samples through unchanged.
            2. Use Pillow to read image width, height, and color mode and write them into metrics.
            3. Append a low_resolution_image issue when width or height is below the configured threshold.

        Args:
            item: Image or non-image data item in the current workflow.

        Returns:
            DataItem: Data item with image quality metrics and issue records written.

        Examples:
            >>> ImageQualityInspectOperator({"min_width": 64}).config["min_width"]
            64"""
        if item.modality != "image":  # Cross-modality guard: image quality inspection only handles image samples.
            return item

        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Pillow is required for image parsing") from exc

        path = Path(item.payload["path"])
        min_width = int(self.config.get("min_width", 64))
        min_height = int(self.config.get("min_height", 64))
        with Image.open(path) as image:
            width, height = image.size
            item.metrics.update({"width": width, "height": height, "mode": image.mode})
            if width < min_width or height < min_height:  # Low resolution: record an image-quality issue that may affect OCR.
                item.issues.append({"type": "low_resolution_image", "message": f"image too small: {width}x{height}"})

        return item
