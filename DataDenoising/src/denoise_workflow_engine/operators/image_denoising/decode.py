from __future__ import annotations

from denoise_workflow_engine.utilities.image.base import ImageOperator
from denoise_workflow_engine.utilities.image.decode import probe_image_readability


class ImageDecodeOperator(ImageOperator):
    operator_name: str = "image_decode"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Check whether an image sample can be read successfully.

        Business logic:
            1. Resolve the image path and verify that the file exists.
            2. Delegate image decoding to the shared helper.
            3. Record readability metrics and decode-related issues.

        Args:
            item (dict): Current sample dictionary.

        Returns:
            dict: Updated sample dictionary.

        Examples:
            >>> ImageDecodeOperator({}).operator_name
            'image_decode'
        """
        if self.should_skip(item):  # Skip work when an earlier operator already ruled out image processing.
            return item

        path = self.image_path(item)
        if not path.exists():  # Record a missing-file issue when the image path does not exist.
            self.add_issue(item, "image_missing")
            self.set_metric(item, "image_readable", False)
            return item

        try:
            readable, image_bytes = probe_image_readability(path)
            self.set_metric(item, "image_readable", readable)
            if image_bytes is not None:  # Preserve the fallback size metric when Pillow is unavailable.
                self.set_metric(item, "image_bytes", image_bytes)
        except Exception:
            self.add_issue(item, "decode_failed")
            self.set_metric(item, "image_readable", False)

        return item
