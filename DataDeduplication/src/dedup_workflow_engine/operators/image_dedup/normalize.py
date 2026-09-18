from dedup_workflow_engine.utilities.image.shared import *  # noqa: F403

class ImageNormalizeForDedupOperator(BaseOperator):
    operator_name = "image_normalize_for_dedup"  # Workflow config: operator name for resolving image paths and basic dimensions in the image-dedup workflow.

    def process_dataset(self, items: list[dict[str, Any]], context: dict[str, Any]) -> list[dict[str, Any]]:
        """Normalize image sample paths and collect basic metadata.

        Business logic:
            1. Resolve the absolute path from payload.image_path.
            2. Validate that the path exists and record file size.
            3. Try reading image dimensions and mark image_decode_failed on failure.

        Args:
            items (list[dict[str, Any]]): Image sample list.
            context (dict[str, Any]): Shared workflow context, expected to contain cwd.

        Returns:
            list[dict[str, Any]]: Sample list updated with image_path_abs and basic metrics.

        Examples:
            >>> ImageNormalizeForDedupOperator({}).process_dataset([], {"cwd": "."})
            []
        """
        for item in items:  # Every image sample must resolve its path first so downstream image operators can reuse image_path_abs.
            path = self.resolve_path(item, context, "image_path")
            if path is None:  # Samples missing an image path cannot enter the image-dedup pipeline.
                self.add_issue(item, "missing_image_path")
                item["action"] = "review"
                continue
            self.set_intermediate(item, "image_path_abs", str(path))
            if not path.exists():  # Keep the sample but move it to review when the file does not exist.
                self.add_issue(item, "image_not_found")
                item["action"] = "review"
                continue
            size = path.stat().st_size
            self.set_metric(item, "file_size", size)
            dimensions = image_dimensions(path)
            if dimensions:  # Write metrics needed by quality selection after dimensions are decoded successfully.
                width, height = dimensions
                self.set_metric(item, "image_width", width)
                self.set_metric(item, "image_height", height)
            else:
                self.add_issue(item, "image_decode_failed")
        return items
