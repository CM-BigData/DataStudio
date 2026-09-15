from typing import Any
from denoise_workflow_engine.utilities.image_text_pair.base import *  # noqa: F403

class PairStructureCheckOperator(BaseOperator):
    operator_name: str = "pair_structure_check"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Validate the basic structure of one image-text-pair sample.

        Business logic:
            1. Skip non-pair modalities.
            2. Check whether both image path and text are present.
            3. Record structure-related issues and caption length metrics.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if item.get("modality") != "image_text_pair":  # Run this operator only for image-text-pair samples.
            return item
        payload = item.get("payload", {})
        text = str(payload.get("text", "") or "").strip()
        image_path = str(payload.get("image_path", "") or "").strip()
        if not image_path:  # Flag a structure issue when the pair sample lacks an image path.
            self.add_issue(item, "pair_missing_image")
        if not text:  # Flag a structure issue when the pair sample lacks text.
            self.add_issue(item, "pair_missing_text")
        self.set_metric(item, "caption_length", len(text))
        return item
