from __future__ import annotations

from pathlib import Path

from PIL import Image

from quality_eval.utilities.image.shared import *  # noqa: F403


class ImageLosslessEvalOperator(BaseOperator):
    operator_name: str = "image_lossless_eval"  # Registered operator name used to detect truncated or broken image files.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Check whether the image file is complete and non-broken.

        Business logic:
            1. Read the image path from the sample payload and skip when it is missing.
            2. Reuse file-level checks for missing files and zero-byte files before validation.
            3. Apply the reference broken-image logic: JPEG tail marker check plus Pillow verify.
            4. Write score/reason metrics and append `image_broken` when the file is incomplete or corrupted.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample updated with lossless-check metrics and issues.

        Examples:
            >>> sample = {"payload": {}, "metrics": {}, "issues": []}
            >>> ImageLosslessEvalOperator({}).process(sample)["metrics"]["image_lossless_score"] is None
            True
        """
        image_path = str(item.get("payload", {}).get("image_path", ""))
        if not image_path:  # Upstream decode owns the missing-path issue, so this operator only writes empty metrics.
            self.metric(item, "image_lossless_score", None)
            self.metric(item, "image_lossless_ok", False)
            self.metric(item, "image_lossless_reason", "missing_image_path")
            return item

        path = Path(image_path)
        if not path.exists():  # Upstream decode owns the missing-file issue, so keep this operator non-duplicative.
            self.metric(item, "image_lossless_score", None)
            self.metric(item, "image_lossless_ok", False)
            self.metric(item, "image_lossless_reason", "image_not_found")
            return item

        if path.stat().st_size == 0:  # Empty files are always broken and should be surfaced explicitly.
            self.metric(item, "image_lossless_score", 0.0)
            self.metric(item, "image_lossless_ok", False)
            self.metric(item, "image_lossless_reason", "file_size_zero")
            self.add_issue(item, "image_broken")
            return item

        is_broken, reason = self._is_broken_image(path)
        self.metric(item, "image_lossless_score", 0.0 if is_broken else 1.0)
        self.metric(item, "image_lossless_ok", not is_broken)
        self.metric(item, "image_lossless_reason", reason)
        if is_broken:  # Broken or truncated files fail the lossless-integrity check even if metadata is partially readable.
            self.add_issue(item, "image_broken")
        return item

    def _is_broken_image(self, path: Path) -> tuple[bool, str]:
        """Detect whether an image file is broken using file-signature and Pillow validation.

        Business logic:
            1. Read the raw bytes and detect JPEG headers.
            2. When the file is JPEG/JFIF/Exif, require the standard JPEG tail marker.
            3. Reopen the file with Pillow and call `verify` as the final integrity check.

        Args:
            path (Path): Image path.

        Returns:
            tuple[bool, str]: Broken flag and reason string.

        Examples:
            >>> isinstance(ImageLosslessEvalOperator({})._is_broken_image(Path(__file__))[0], bool)
            True
        """
        try:
            with path.open("rb") as file_object:
                buffer = file_object.read()
                if buffer.startswith(b"\xff\xd8") and buffer[6:10] in (b"JFIF", b"Exif"):
                    if not buffer.rstrip(b"\0\r\n").endswith(b"\xff\xd9"):  # Truncated JPEGs often miss the end-of-image marker.
                        return True, "jpeg_tail_marker_missing"
                file_object.seek(0)
                try:
                    image = Image.open(file_object)
                    image.verify()
                except Exception as exc:
                    return True, f"image_verify_failed:{exc}"
            return False, "image_complete"
        except Exception as exc:
            return True, f"image_process_failed:{exc}"
