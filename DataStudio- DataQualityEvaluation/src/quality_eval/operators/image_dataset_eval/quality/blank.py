from quality_eval.utilities.image.shared import *  # noqa: F403


class ImageBlankEvalOperator(BaseOperator):
    operator_name: str = "image_blank_eval"  # Registered operator name used to detect blank, solid-color, and near-empty images.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Detect white, black, near-solid, and blank-content images.

        Business logic:
            1. Read grayscale statistics produced by `image_decode_eval`.
            2. Write brightness, contrast, dynamic-range, and dominance metrics.
            3. Detect pure white, pure black, near-solid, and blank-content cases in priority order.
            4. Skip evaluation when the image is unreadable so decode failures remain separate.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample updated with blank-image metrics and issues.

        Examples:
            >>> sample = {"intermediate": {"grayscale_stats": {"mean_intensity": 255, "std_intensity": 0, "dynamic_range": 0, "dominant_ratio": 1}}, "metrics": {}, "issues": []}
            >>> ImageBlankEvalOperator({}).process(sample)["issues"]
            ['pure_white_image', 'blank_content_image']
        """
        if item.get("metrics", {}).get("readable") is False:  # Unreadable images do not have stable pixel statistics, so skip blank-image evaluation.
            return item
        stats = item.get("intermediate", {}).get("grayscale_stats")
        if not isinstance(stats, dict):  # Backfill empty metrics when decode statistics are missing instead of interrupting the workflow.
            self.metric(item, "blank_content_score", None)
            self.metric(item, "blank_image_detected", False)
            return item

        mean_intensity = float(stats.get("mean_intensity", 0))
        std_intensity = float(stats.get("std_intensity", 0))
        dynamic_range = int(stats.get("dynamic_range", 0))
        dominant_ratio = float(stats.get("dominant_ratio", 0))
        min_intensity = int(stats.get("min_intensity", 0))
        max_intensity = int(stats.get("max_intensity", 0))

        pure_white_threshold = float(self.rules.get("pure_white_mean_threshold", 250))
        pure_black_threshold = float(self.rules.get("pure_black_mean_threshold", 5))
        pure_color_std_threshold = float(self.rules.get("pure_color_std_threshold", 0.5))
        near_solid_std_threshold = float(self.rules.get("near_solid_std_threshold", 6.0))
        near_solid_range_threshold = int(self.rules.get("near_solid_range_threshold", 18))
        near_solid_dominant_ratio_threshold = float(self.rules.get("near_solid_dominant_ratio_threshold", 0.12))
        blank_std_threshold = float(self.rules.get("blank_content_std_threshold", 12.0))
        blank_range_threshold = int(self.rules.get("blank_content_range_threshold", 40))
        blank_bright_threshold = float(self.rules.get("blank_content_mean_threshold", 235))
        blank_dark_threshold = float(self.rules.get("blank_content_dark_mean_threshold", 20))
        blank_dominant_ratio_threshold = float(self.rules.get("blank_content_dominant_ratio_threshold", 0.55))

        is_pure_white = max_intensity >= pure_white_threshold and min_intensity >= pure_white_threshold and std_intensity <= pure_color_std_threshold
        is_pure_black = max_intensity <= pure_black_threshold and std_intensity <= pure_color_std_threshold
        is_near_solid = dynamic_range <= near_solid_range_threshold and std_intensity <= near_solid_std_threshold and dominant_ratio >= near_solid_dominant_ratio_threshold
        is_blank_content = std_intensity <= blank_std_threshold and (
            mean_intensity >= blank_bright_threshold or mean_intensity <= blank_dark_threshold
        ) and (
            dynamic_range <= blank_range_threshold or dominant_ratio >= blank_dominant_ratio_threshold
        )

        blank_score = max(
            dominant_ratio * 100,
            max(0.0, (1 - min(std_intensity, 50.0) / 50.0)) * 100,
        )
        blank_detected = False

        self.metric(item, "mean_intensity", round(mean_intensity, 4))
        self.metric(item, "std_intensity", round(std_intensity, 4))
        self.metric(item, "dynamic_range", dynamic_range)
        self.metric(item, "dominant_intensity_ratio", round(dominant_ratio, 6))

        if is_pure_white:
            self.add_issue(item, "pure_white_image")
            blank_detected = True
        if is_pure_black:
            self.add_issue(item, "pure_black_image")
            blank_detected = True
        if is_near_solid and not (is_pure_white or is_pure_black):
            self.add_issue(item, "near_solid_color_image")
            blank_detected = True
        if is_blank_content:
            self.add_issue(item, "blank_content_image")
            blank_detected = True

        self.metric(item, "blank_content_score", round(blank_score, 2))
        self.metric(item, "blank_image_detected", blank_detected)
        return item
