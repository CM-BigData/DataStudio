from typing import Any
from denoise_workflow_engine.utilities.image.base import *  # noqa: F403

try:
    import imagehash
except ImportError:  # pragma: no cover
    imagehash = None

class QRCodeDetectOperator(ImageOperator):
    operator_name: str = "qr_code_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect QR codes in one image sample.

        Business logic:
            1. Skip unreadable or missing images.
            2. Prefer OpenCV QR detection and fall back to a local corner-pattern heuristic.
            3. Record detection metrics and issues when a QR code is confirmed or suspected.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or "decode_failed" in issues or "image_missing" in issues:  # Skip QR detection when the image is unreadable or missing.
            return item
        path = self.image_path(item)
        detected = False
        decoded_text = ""
        method = "local_unavailable"
        if cv2 is not None:  # Prefer the OpenCV decoder when it is available.
            try:
                image = cv2.imread(str(path))
                if image is not None:  # Run pixel-level detection only after the image loads successfully.
                    detector = cv2.QRCodeDetector()
                    decoded_text, points, _ = detector.detectAndDecode(image)
                    detected = bool(decoded_text)
                    if points is not None and not decoded_text:  # Mark suspected QR codes when locator points are found without decoded content.
                        self.set_metric(item, "qr_suspected", True)
                    method = "opencv_qrcode_detector"
            except Exception:
                method = "opencv_qrcode_failed"
        if not detected:  # Fall back to a local corner-pattern heuristic when OpenCV does not confirm a QR code.
            suspected, fallback_method = self._fallback_detect(path)
            if suspected:  # Record suspected results when the heuristic finds QR-like corner patterns.
                self.set_metric(item, "qr_suspected", True)
                self.set_metric(item, "qr_suspected_detection_method", fallback_method)
                self.set_metric(item, "qr_detection_confidence", 0.25)
        self.set_metric(item, "qr_detected", detected)
        self.set_metric(item, "qr_detection_method", method)
        if detected:  # Write confidence only for confirmed detections.
            self.set_metric(item, "qr_detection_confidence", 0.95)
        if decoded_text:  # Persist decoded text for auditing when available.
            self.set_metric(item, "qr_decoded_text", decoded_text[:200])
        if detected:  # Add the issue only for confirmed QR detections.
            self.add_issue(item, "qrcode_detected")
        return item

    def _fallback_detect(self, path: Path) -> tuple[bool, str]:
        """Detect QR-like patterns with a local heuristic.

        Business logic:
            1. Resize the image into a grayscale binary view.
            2. Evaluate corner darkness and transition density.
            3. Return whether the image looks QR-like and the heuristic label.

        Args:
                path (Path): File path.

        Returns:
            tuple[bool, str]: Heuristic detection result and method label.

        Examples:
            >>> _fallback_detect
            _fallback_detect
        """
        if Image is None or np is None:  # The fallback is unavailable without Pillow and NumPy.
            return False, "fallback_unavailable"
        try:
            with Image.open(path) as image:
                gray = image.convert("L").resize((256, 256))
            arr = np.array(gray)
            binary = arr < 96
            corner_size = 92
            corners = [
                binary[:corner_size, :corner_size],
                binary[:corner_size, -corner_size:],
                binary[-corner_size:, :corner_size],
                binary[-corner_size:, -corner_size:],
            ]
            dark_ratios = [float(corner.mean()) for corner in corners]
            transition_scores = []
            for corner in corners:  # Evaluate black-white transitions in each corner, where QR locators usually cluster.
                transition_scores.append(float(np.abs(np.diff(corner.astype("int8"), axis=0)).mean()))
                transition_scores.append(float(np.abs(np.diff(corner.astype("int8"), axis=1)).mean()))
            detected = max(dark_ratios) > 0.18 and max(transition_scores) > 0.16
            return detected, "fallback_corner_pattern"
        except Exception:
            return False, "fallback_failed"

class WatermarkDetectOperator(ImageOperator):
    operator_name: str = "watermark_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect watermark-like overlays in one image sample.

        Business logic:
            1. Analyze corner regions for overlay-like brightness, darkness, and edge patterns.
            2. Combine region scores with a dark-overlay heuristic.
            3. Record watermark metrics and issues when a watermark is detected.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or Image is None or np is None or "decode_failed" in issues or "image_missing" in issues:  # Skip watermark detection when required image capabilities are unavailable.
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB").resize((384, 384))
            arr = np.array(rgb)
            h, w, _ = arr.shape
            crop_h = max(64, h // 4)
            crop_w = max(96, w // 3)
            crops = {
                "top_left": arr[:crop_h, :crop_w],
                "top_right": arr[:crop_h, -crop_w:],
                "bottom_left": arr[-crop_h:, :crop_w],
                "bottom_right": arr[-crop_h:, -crop_w:],
            }
            scores = {}
            overlay_scores = {}
            for name, crop in crops.items():  # Evaluate each corner because watermarks and logos often appear near edges.
                gray = np.mean(crop, axis=2).astype("uint8")
                bright_ratio = float((gray > 205).mean())
                dark_ratio = float((gray < 55).mean())
                local_edges = edge_density(gray)
                local_std = float(gray.std() / 255.0)
                scores[name] = round(local_edges * 1.8 + local_std * 0.8 + min(bright_ratio + dark_ratio, 0.4), 4)
                overlay_scores[name] = {
                    "mean": round(float(gray.mean()), 4),
                    "dark_ratio": round(float((gray < 70).mean()), 4),
                    "std": round(float(gray.std()), 4),
                }
            score = max(scores.values()) if scores else 0.0
            overlay_detected = self._detect_dark_overlay(overlay_scores)
            detected = score >= float(self.config.get("min_watermark_score", 0.20)) or overlay_detected
            self.set_metric(item, "watermark_score", round(score, 4))
            self.set_metric(item, "watermark_region_scores", scores)
            self.set_metric(item, "watermark_overlay_scores", overlay_scores)
            self.set_metric(item, "watermark_dark_overlay_detected", overlay_detected)
            self.set_metric(item, "watermark_detection_method", "corner_overlay_heuristic")
            self.set_metric(item, "watermark_detection_confidence", 0.4 if detected else 0.0)
            if imagehash is not None:  # Note perceptual-hash support when imagehash is available.
                self.set_metric(item, "watermark_perceptual_hash_method", "imagehash_phash")
            if detected:  # Add the issue only for confirmed watermark detections.
                self.add_issue(item, "watermark_detected")
        except Exception:
            self.add_issue(item, "watermark_detect_failed")
        return item

    def _detect_dark_overlay(self, overlay_scores: dict[str, dict[str, float]]) -> bool:
        """Detect dark overlay patterns from corner statistics.

        Business logic:
            1. Compare each corner against the brightness baseline of the others.
            2. Use dark-ratio and variance thresholds to detect overlay-like regions.
            3. Return whether a dark overlay is likely present.

        Args:
                overlay_scores (dict[str, dict[str, float]]): Corner-overlay statistics.

        Returns:
            bool: Whether a dark overlay is detected.

        Examples:
            >>> _detect_dark_overlay
            _detect_dark_overlay
        """
        if len(overlay_scores) < 2:  # Require at least two corners before comparing overlays.
            return False
        means = {name: values["mean"] for name, values in overlay_scores.items()}
        for name, values in overlay_scores.items():  # Compare each corner against the others to detect dark overlays.
            other_means = [value for other, value in means.items() if other != name]
            if not other_means:  # Skip overlay checks when no brightness baseline exists.
                continue
            local_mean = values["mean"]
            dark_ratio = values["dark_ratio"]
            local_std = values["std"]
            reference_mean = sorted(other_means)[len(other_means) // 2]
            if dark_ratio >= 0.5 and local_std >= 45.0 and local_mean <= reference_mean - 25.0:  # Mark overlays when darkness, variance, and contrast all exceed thresholds.
                return True
        return False

class LogoDetectOperator(ImageOperator):
    operator_name: str = "logo_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect logo-like corner patterns in one image sample.

        Business logic:
            1. Analyze saturated, high-contrast corner regions.
            2. Score each corner for logo-like color concentration.
            3. Record logo metrics and issues when a logo is detected.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or Image is None or np is None or "decode_failed" in issues or "image_missing" in issues:  # Skip logo detection when required image capabilities are unavailable.
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB").resize((384, 384))
            arr = np.array(rgb).astype("float32")
            h, w, _ = arr.shape
            crop_h = max(64, h // 5)
            crop_w = max(64, w // 5)
            crops = {
                "top_left": arr[:crop_h, :crop_w],
                "top_right": arr[:crop_h, -crop_w:],
                "bottom_left": arr[-crop_h:, :crop_w],
                "bottom_right": arr[-crop_h:, -crop_w:],
            }
            scores = {}
            for name, crop in crops.items():  # Evaluate each corner because logos often appear near edges.
                max_channel = crop.max(axis=2)
                min_channel = crop.min(axis=2)
                saturation = (max_channel - min_channel) / np.maximum(max_channel, 1)
                saturated_ratio = float((saturation > 0.55).mean())
                contrast = float(np.mean(max_channel - min_channel) / 255.0)
                scores[name] = round(saturated_ratio * 0.8 + contrast * 0.5, 4)
            score = max(scores.values()) if scores else 0.0
            detected = score >= float(self.config.get("min_logo_score", 0.18))
            self.set_metric(item, "logo_score", round(score, 4))
            self.set_metric(item, "logo_region_scores", scores)
            self.set_metric(item, "logo_detection_method", "corner_saturation_heuristic")
            self.set_metric(item, "logo_detection_confidence", 0.35 if detected else 0.0)
            if detected:  # Add the issue only for confirmed logo detections.
                self.add_issue(item, "logo_detected")
        except Exception:
            self.add_issue(item, "logo_detect_failed")
        return item
