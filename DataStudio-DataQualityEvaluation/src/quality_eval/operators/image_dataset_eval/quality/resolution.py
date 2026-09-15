from quality_eval.utilities.image.shared import *  # noqa: F403


class ImageResolutionEvalOperator(BaseOperator):
    operator_name: str = "image_resolution_eval"  # Registered operator name used to check image width and height thresholds.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check whether image resolution meets minimum width and height requirements.

        Business logic:
            1. Read image width and height from decoding intermediates.
            2. Append `width_too_small` when width exists and is below the minimum threshold.
            3. Append `height_too_small` when height exists and is below the minimum threshold.
            4. Write a boolean metric indicating whether both dimensions satisfy the thresholds.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with resolution metrics and issues written back.

        Examples:
            >>> sample = {"intermediate": {"image_size": [10, 10]}, "metrics": {}, "issues": []}
            >>> ImageResolutionEvalOperator({}).process(sample)["issues"]
            ['width_too_small', 'height_too_small']
        """
        width, height = item.get("intermediate", {}).get("image_size", [0, 0])
        if width and width < int(self.rules.get("min_width", 224)):  # Very small width reduces image-sample usability.
            self.add_issue(item, "width_too_small")
        if height and height < int(self.rules.get("min_height", 224)):  # Very small height reduces image-sample usability.
            self.add_issue(item, "height_too_small")
        self.metric(item, "resolution_ok", width >= int(self.rules.get("min_width", 224)) and height >= int(self.rules.get("min_height", 224)))
        return item


class ImageAspectRatioEvalOperator(BaseOperator):
    operator_name: str = "image_aspect_ratio_eval"  # Registered operator name used to detect abnormal image aspect ratios.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check whether image aspect ratio falls within the configured range.

        Business logic:
            1. Read image width and height from intermediates.
            2. Record an empty metric and return when width or height is missing.
            3. Compute the aspect ratio and write it to `aspect_ratio`.
            4. Append `aspect_ratio_abnormal` when the ratio is outside the configured bounds.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with aspect-ratio metrics and issues written back.

        Examples:
            >>> sample = {"intermediate": {"image_size": [1000, 10]}, "metrics": {}, "issues": []}
            >>> ImageAspectRatioEvalOperator({}).process(sample)["issues"]
            ['aspect_ratio_abnormal']
        """
        width, height = item.get("intermediate", {}).get("image_size", [0, 0])
        if not width or not height:  # Aspect ratio cannot be computed reliably when decoding failed or dimensions are missing.
            self.metric(item, "aspect_ratio", None)
            return item
        ratio = width / height
        self.metric(item, "aspect_ratio", round(ratio, 4))
        min_ratio = float(self.rules.get("min_aspect_ratio", 0.2))
        max_ratio = float(self.rules.get("max_aspect_ratio", 5.0))
        if ratio < min_ratio or ratio > max_ratio:  # Extreme aspect ratios usually require manual review or removal.
            self.add_issue(item, "aspect_ratio_abnormal")
        return item
