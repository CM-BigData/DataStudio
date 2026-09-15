from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.image_synthesis import validate_image_quality


class ImageQualityValidateOperator(BaseOperator):
    operator_name = "image_quality_validate"  # Registry name for the image-quality validation workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Validate image output quality

        Business logic:
            1. Skip non-image task samples
            2. Check whether the image path exists
            3. Read dimensions and record low-resolution issues

        Args:
            item (GenerationItem): Sample to validate.

        Returns:
            GenerationItem: Sample carrying image-quality issues.

        Examples:
            >>> ImageQualityValidateOperator().operator_name
            'image_quality_validate'
        """
        if item.task_type != "image":  # Image-quality rules only apply to image tasks.
            return item

        min_width = int(self.config.get("min_width", 128))
        min_height = int(self.config.get("min_height", 128))
        item.issues.extend(validate_image_quality(item.generated.get("image_path"), min_width, min_height))
        return item
