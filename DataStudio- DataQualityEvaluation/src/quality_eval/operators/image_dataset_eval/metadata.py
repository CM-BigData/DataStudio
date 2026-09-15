from quality_eval.utilities.image.shared import *  # noqa: F403

class ImageDecodeEvalOperator(BaseOperator):
    operator_name: str = "image_decode_eval"  # Registered operator name used to read images and extract basic metadata.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Read an image and extract size, format, hash, and sharpness.

        Business logic:
            1. Read the image path from `payload.image_path`.
            2. Record unreadable metrics and matching issues when the path is missing or the file does not exist.
            3. Use `verify` first to validate file readability.
            4. Reopen the image to extract size, format, content hash, and sharpness.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with image intermediate values, metrics, and issues written back.

        Examples:
            >>> sample = {"payload": {}, "metrics": {}, "issues": []}
            >>> ImageDecodeEvalOperator({}).process(sample)["issues"]
            ['missing_image_path']
        """
        image_path = item.get("payload", {}).get("image_path")
        if not image_path:  # No image-quality checks can continue without an image path.
            self.add_issue(item, "missing_image_path")
            self.metric(item, "readable", False)
            return item
        path = Path(image_path)
        if not path.exists():  # The sample is unusable when the manifest points to a missing file.
            self.add_issue(item, "image_not_found")
            self.metric(item, "readable", False)
            return item
        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                width, height = image.size
                item.setdefault("intermediate", {})["image_size"] = [width, height]
                item["intermediate"]["image_format"] = (image.format or path.suffix.lstrip(".")).lower()
                item["intermediate"]["image_hash"] = _average_hash(image)
                item["intermediate"]["sharpness"] = _sharpness(image)
                item["intermediate"]["grayscale_stats"] = _grayscale_statistics(image)
                self.metric(item, "width", width)
                self.metric(item, "height", height)
                self.metric(item, "format", item["intermediate"]["image_format"])
                self.metric(item, "readable", True)
        except Exception:
            self.add_issue(item, "image_unreadable")
            self.metric(item, "readable", False)
        return item

class ImageFormatEvalOperator(BaseOperator):
    operator_name: str = "image_format_eval"  # Registered operator name used to validate the allowed image-format list.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Validate whether the image format is supported.

        Business logic:
            1. Read allowed formats from rules, defaulting to jpg, jpeg, and png.
            2. Read the actual format from image-decoding intermediates.
            3. Normalize `jpg` to `jpeg` for compatibility with Pillow format names.
            4. Append `unsupported_format` when a non-empty format is not in the allowlist.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample with format-support metrics and issues written back.

        Examples:
            >>> sample = {"intermediate": {"image_format": "bmp"}, "metrics": {}, "issues": []}
            >>> ImageFormatEvalOperator({}).process(sample)["issues"]
            ['unsupported_format']
        """
        allowed = {str(value).lower() for value in self.rules.get("allowed_formats", ["jpg", "jpeg", "png"])}
        image_format = str(item.get("intermediate", {}).get("image_format", "")).lower()
        if image_format == "jpg":  # Pillow often uses `jpeg` while configs often use `jpg`, so normalize them for comparison.
            image_format = "jpeg"
        normalized_allowed = {"jpeg" if value == "jpg" else value for value in allowed}
        supported = not image_format or image_format in normalized_allowed
        self.metric(item, "format_supported", supported)
        if image_format and not supported:  # Mark unsupported only when a format was identified but is outside the allowlist.
            self.add_issue(item, "unsupported_format")
        return item
