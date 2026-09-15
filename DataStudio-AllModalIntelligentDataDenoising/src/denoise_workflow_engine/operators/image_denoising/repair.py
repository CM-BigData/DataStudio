from typing import Any
from denoise_workflow_engine.utilities.image.base import *  # noqa: F403
from denoise_workflow_engine.runtime.loader import safe_child_path

class ImageRepairOperator(ImageOperator):
    operator_name: str = "image_repair"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Repair recoverable quality issues in one image sample.

        Business logic:
            1. Skip repair for missing, unreadable, or hard-fail images.
            2. Apply deterministic repairs for exposure, blur, and noise issues.
            3. Save the repaired image and update payload, intermediate paths, and repair metrics.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = set(item.get("issues", []))
        if self.should_skip(item) or Image is None or ImageEnhance is None or ImageOps is None:  # Skip repair when image processing dependencies or prior workflow conditions block it.
            return item
        hard_skip = set(
            self.config.get(
                "skip_issues",
                ["image_missing", "decode_failed", "qrcode_detected", "safety_risk", "subject_missing", "pure_color"],
            )
        )
        if issues & hard_skip:  # Do not attempt repair when hard-fail issues are present.
            self.set_metric(item, "image_repair_applied", False)
            self.set_metric(item, "image_repair_skip_reason", sorted(issues & hard_skip))
            return item
        repair_triggers = set(self.config.get("repair_triggers", ["under_exposure", "over_exposure", "blur", "high_noise"]))
        removable_after_repair = set(
            self.config.get(
                "repair_issues",
                [
                    "under_exposure",
                    "over_exposure",
                    "blur",
                    "high_noise",
                    "reference_low_psnr",
                    "reference_low_ssim",
                    "reference_severe_difference",
                ],
            )
        )
        if not (issues & repair_triggers):  # Preserve the original image when no repair-trigger issue is present.
            self.set_metric(item, "image_repair_applied", False)
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                repaired = image.convert("RGB")
            if "under_exposure" in issues or "over_exposure" in issues:  # Apply exposure correction for brightness-related issues.
                repaired = ImageOps.autocontrast(repaired)
                repaired = ImageEnhance.Contrast(repaired).enhance(float(self.config.get("contrast_factor", 1.15)))
                repaired = ImageEnhance.Brightness(repaired).enhance(float(self.config.get("brightness_factor", 1.05)))
            if "blur" in issues and ImageFilter is not None:  # Apply sharpening when blur repair is available.
                repaired = repaired.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=3))
            if "high_noise" in issues and ImageFilter is not None:  # Apply median smoothing when noise repair is available.
                repaired = repaired.filter(ImageFilter.MedianFilter(size=3))

            configured_output = self.config.get("output_dir")
            output_dir = (
                self.resolve_runtime_path(str(configured_output), name="image repair output directory")
                if configured_output
                else safe_child_path(self.runtime_run_dir(), "repaired_images", "image repair output directory")
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            target = safe_child_path(
                output_dir,
                f"{self.safe_item_id(item, path.stem)}_repaired.jpg",
                "repaired image path",
            )
            repaired.save(target, quality=92)
            item.setdefault("payload", {})["original_image_path"] = str(path).replace("\\", "/")
            item["payload"]["image_path"] = str(target).replace("\\", "/")
            item.setdefault("intermediate", {})["image_before_repair"] = str(path).replace("\\", "/")
            item["intermediate"]["image_after_repair"] = str(target).replace("\\", "/")
            item["issues"] = [issue for issue in item.get("issues", []) if issue not in removable_after_repair]
            self.add_issue(item, "image_repaired")
            self.set_metric(item, "image_repair_applied", True)
            self.set_metric(item, "image_repair_output", str(target).replace("\\", "/"))
        except Exception as exc:
            self.add_issue(item, "image_repair_failed")
            self.set_metric(item, "image_repair_error", str(exc))
        return item
