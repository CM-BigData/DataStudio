from quality_eval.utilities.image.shared import *  # noqa: F403


class AnnotationEvalOperator(BaseOperator):
    operator_name: str = "annotation_eval"  # Registered operator name used to inspect image-label completeness.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check whether an image sample has a complete label.

        Business logic:
            1. Read the label from `meta.label` first and fall back to `payload.label` when missing.
            2. Write the `label_complete` metric.
            3. Append `missing_label` when the label is missing or blank.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with label-completeness metrics and issues written back.

        Examples:
            >>> sample = {"payload": {}, "meta": {}, "metrics": {}, "issues": []}
            >>> AnnotationEvalOperator({}).process(sample)["issues"]
            ['missing_label']
        """
        label = item.get("meta", {}).get("label", item.get("payload", {}).get("label"))
        complete = label is not None and str(label).strip() != ""
        self.metric(item, "label_complete", complete)
        if not complete:  # Missing labels affect supervised training and evaluation usability.
            self.add_issue(item, "missing_label")
        return item


class AnnotationBBoxEvalOperator(AnnotationEvalOperator):
    operator_name: str = "annotation_bbox_eval"  # Registered operator name used to inspect image bbox annotation bounds.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check image-label completeness and bbox boundary validity.

        Business logic:
            1. Reuse the label-completeness check first.
            2. Do not append boundary issues when bbox data is missing.
            3. Check coordinate bounds only when both image size and a four-value bbox exist.
            4. Append `bbox_out_of_bounds` when coordinates are out of bounds or invalid.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with label and bbox issues written back.

        Examples:
            >>> sample = {"payload": {}, "meta": {"label": "cat"}, "intermediate": {}, "metrics": {}, "issues": []}
            >>> AnnotationBBoxEvalOperator({}).process(sample)["issues"]
            []
        """
        item = super().process(item)
        bbox = item.get("meta", {}).get("bbox")
        if not bbox:  # Classification samples without bbox data should not be misclassified as bbox out of bounds.
            return item
        width, height = item.get("intermediate", {}).get("image_size", [0, 0])
        if width and height and len(bbox) == 4:  # Boundary checks require both valid image size and a four-value box.
            x1, y1, x2, y2 = bbox
            if x1 < 0 or y1 < 0 or x2 > width or y2 > height or x2 <= x1 or y2 <= y1:  # Out-of-bounds or reversed coordinates make the annotation invalid.
                self.add_issue(item, "bbox_out_of_bounds")
        return item
