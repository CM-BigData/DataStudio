from quality_eval.utilities.image.shared import *  # noqa: F403


class ImageBlurEvalOperator(BaseOperator):
    operator_name: str = "image_blur_eval"  # Registered operator name used to inspect image sharpness.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect blurry images from the sharpness threshold.

        Business logic:
            1. Read `sharpness` written during decoding.
            2. Copy the sharpness value into sample metrics.
            3. Append `blurred_image` when the value exists and is below the threshold.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with sharpness metrics and issues written back.

        Examples:
            >>> sample = {"intermediate": {"sharpness": 0}, "metrics": {}, "issues": []}
            >>> ImageBlurEvalOperator({}).process(sample)["issues"]
            ['blurred_image']
        """
        sharpness = item.get("intermediate", {}).get("sharpness")
        self.metric(item, "sharpness", sharpness)
        if sharpness is not None and sharpness < float(self.rules.get("blur_threshold", 100)):  # Images below the sharpness threshold may be unusable for training.
            self.add_issue(item, "blurred_image")
        return item
