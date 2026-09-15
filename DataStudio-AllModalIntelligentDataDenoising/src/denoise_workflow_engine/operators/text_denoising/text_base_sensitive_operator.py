from denoise_workflow_engine.utilities.text.base import TextOperator
from denoise_workflow_engine.operators.text_denoising.pipelines import BaseTextSensitivePipeline


class BaseTextSensitiveOperator(TextOperator):
    pipeline: BaseTextSensitivePipeline  # Text-sensitive-information pipeline responsible for assessment and governance orchestration.

    def process(self, item: dict) -> dict:
        """Process one workflow item through the text-sensitive-information pipeline.

        Business logic:
            1. Decide whether the current sample should skip text-sensitive-information processing.
            2. Run the pipeline to assess and govern the text.
            3. Write issues, metrics, and text back when any sensitive type is detected.

        Args:
            item (dict): Current workflow sample.

        Returns:
            dict: Updated workflow sample.

        Examples:
            >>> BaseTextSensitiveOperator({}).process({"modality": "image", "payload": {}})
            {'modality': 'image', 'payload': {}}
        """
        if self.should_skip(item):  # Non-text samples do not enter text-sensitive-information processing.
            return item
        result = self.pipeline.run(self.get_text(item))
        hit_types = result.hit_types
        if hit_types:  # Write workflow-visible results only when sensitive text is detected.
            self.add_issue(item, "text_sensitive_masked")
            self.set_metric(item, "text_sensitive_types", hit_types)
            self.set_text(item, result.text)
        return item
