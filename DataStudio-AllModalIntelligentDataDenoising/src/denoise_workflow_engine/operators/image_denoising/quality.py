from typing import Any
from denoise_workflow_engine.utilities.image.base import *  # noqa: F403

try:
    from skimage.metrics import peak_signal_noise_ratio, structural_similarity
except ImportError:  # pragma: no cover
    peak_signal_noise_ratio = None
    structural_similarity = None

class BlurDetectOperator(ImageOperator):
    operator_name: str = "blur_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect blur in one image sample.

        Business logic:
            1. Read the image through OpenCV when available, otherwise use a fallback thumbnail heuristic.
            2. Compute a sharpness score and record the method used.
            3. Add a blur issue when sharpness falls below the configured threshold.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or Image is None or "decode_failed" in issues or "image_missing" in issues:  # Skip blur detection when the image is missing, unreadable, or Pillow is unavailable.
            return item
        path = self.image_path(item)
        try:
            if cv2 is not None:  # Prefer the OpenCV path when available.
                image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if image is None:  # Abort the OpenCV path when the image cannot be read.
                    raise ValueError("opencv_read_failed")
                sharpness = float(cv2.Laplacian(image, cv2.CV_64F).var())
                method = "opencv_laplacian_variance"
            else:
                with Image.open(path) as image_file:
                    gray = image_file.convert("L").resize((64, 64))
                    pixels = list(gray.getdata())
                diffs = []
                width = 64
                for idx, pixel in enumerate(pixels):  # Estimate horizontal and vertical edge strength from the thumbnail.
                    if idx % width != width - 1:  # Skip last-column pixels to avoid wraparound edges.
                        diffs.append(abs(pixel - pixels[idx + 1]))
                    if idx + width < len(pixels):  # Compare against the pixel below when it exists.
                        diffs.append(abs(pixel - pixels[idx + width]))
                sharpness = mean(diffs) if diffs else 0.0
                method = "fallback_neighbor_difference"
            self.set_metric(item, "sharpness", round(sharpness, 4))
            self.set_metric(item, "sharpness_method", method)
            if sharpness < float(self.config.get("min_sharpness", 100.0 if cv2 is not None else 4.0)):  # Flag blur when sharpness is below the configured threshold.
                self.add_issue(item, "blur")
        except Exception:
            self.add_issue(item, "decode_failed")
        return item

class ExposureDetectOperator(ImageOperator):
    operator_name: str = "exposure_detect"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Detect exposure problems in one image sample.

        Business logic:
            1. Measure brightness and brightness variance from a grayscale thumbnail.
            2. Record exposure-related metrics.
            3. Add issues for under-exposure, over-exposure, or pure-color images.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or Image is None or "decode_failed" in issues or "image_missing" in issues:  # Skip exposure checks when the image is missing, unreadable, or Pillow is unavailable.
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                gray = image.convert("L").resize((64, 64))
                pixels = list(gray.getdata())
            brightness = mean(pixels)
            variance = mean([(pixel - brightness) ** 2 for pixel in pixels])
            self.set_metric(item, "brightness", round(brightness, 4))
            self.set_metric(item, "brightness_std", round(math.sqrt(variance), 4))
            brightness_std = math.sqrt(variance)
            min_std_for_exposure = float(self.config.get("min_std_for_exposure", 8))
            if brightness < float(self.config.get("min_brightness", 25)) and brightness_std < min_std_for_exposure:  # Flag under-exposure when brightness is too low and variance is weak.
                self.add_issue(item, "under_exposure")
            if brightness > float(self.config.get("max_brightness", 245)) and brightness_std < min_std_for_exposure:  # Flag over-exposure when brightness is too high and variance is weak.
                self.add_issue(item, "over_exposure")
            if brightness_std < float(self.config.get("min_brightness_std", 3)):  # Flag pure-color images when variance is too low.
                self.add_issue(item, "pure_color")
        except Exception:
            self.add_issue(item, "decode_failed")
        return item

class NoiseEstimateOperator(ImageOperator):
    operator_name: str = "noise_estimate"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Estimate visual noise level in one image sample.

        Business logic:
            1. Build a grayscale thumbnail for local noise estimation.
            2. Estimate noise from center-pixel residuals against four-neighbor averages.
            3. Add a high-noise issue when the estimated sigma exceeds threshold.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or Image is None or "decode_failed" in issues or "image_missing" in issues:  # Skip noise estimation when the image is missing, unreadable, or Pillow is unavailable.
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                gray = image.convert("L").resize((96, 96))
                pixels = list(gray.getdata())
            width = 96
            residuals = []
            for y in range(1, width - 1):  # Skip border pixels so all four neighbors exist.
                for x in range(1, width - 1):  # Compute center-pixel residuals within each row.
                    idx = y * width + x
                    center = pixels[idx]
                    neighbors = [
                        pixels[idx - 1],
                        pixels[idx + 1],
                        pixels[idx - width],
                        pixels[idx + width],
                    ]
                    residuals.append(center - mean(neighbors))
            noise_sigma = pstdev(residuals) if residuals else 0.0
            self.set_metric(item, "noise_sigma", round(noise_sigma, 4))
            if noise_sigma > float(self.config.get("max_noise_sigma", 18.0)):  # Flag high noise when sigma exceeds the configured threshold.
                self.add_issue(item, "high_noise")
        except Exception:
            self.add_issue(item, "decode_failed")
        return item

class ReferenceImageQualityOperator(ImageOperator):
    operator_name: str = "reference_image_quality"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Compare the sample image against a reference image.

        Business logic:
            1. Skip processing when no usable reference image is provided.
            2. Compute PSNR, SSIM, and MAE with either scikit-image or local fallbacks.
            3. Add issues when reference similarity falls below configured thresholds.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        if self.should_skip(item) or Image is None:  # Skip work when prior workflow state blocks reference comparison or Pillow is unavailable.
            return item
        ref_value = item.get("payload", {}).get("reference_image_path")
        if not ref_value:  # Skip reference checks when the sample has no reference image.
            return item
        noisy_path = self.image_path(item)
        reference_path = Path(str(ref_value))
        if not noisy_path.exists() or not reference_path.exists():  # Abort paired quality metrics when either image is missing.
            return item
        try:
            with Image.open(noisy_path) as noisy_img, Image.open(reference_path) as ref_img:
                noisy = noisy_img.convert("L")
                ref = ref_img.convert("L").resize(noisy.size)
                max_side = int(self.config.get("max_eval_side", 256))
                noisy.thumbnail((max_side, max_side))
                ref.thumbnail((max_side, max_side))
                noisy_arr = np.array(noisy) if np is not None else None
                ref_arr = np.array(ref) if np is not None else None
                noisy_pixels = noisy_arr.flatten().tolist() if noisy_arr is not None else list(noisy.getdata())
                ref_pixels = ref_arr.flatten().tolist() if ref_arr is not None else list(ref.getdata())
            if peak_signal_noise_ratio is not None and structural_similarity is not None and noisy_arr is not None and ref_arr is not None:  # Prefer scikit-image metrics when the dependency is available.
                psnr = 99.0 if bool(np.array_equal(ref_arr, noisy_arr)) else float(peak_signal_noise_ratio(ref_arr, noisy_arr, data_range=255))
                ssim = float(structural_similarity(ref_arr, noisy_arr, data_range=255))
                method = "scikit_image_metrics"
            else:
                psnr = self._psnr(noisy_pixels, ref_pixels)
                ssim = self._simple_ssim(noisy_pixels, ref_pixels)
                method = "fallback_local_metrics"
            mae = mean(abs(a - b) for a, b in zip(noisy_pixels, ref_pixels)) if noisy_pixels else 0.0
            self.set_metric(item, "reference_psnr", round(psnr, 4))
            self.set_metric(item, "reference_ssim", round(ssim, 4))
            self.set_metric(item, "reference_mae", round(mae, 4))
            self.set_metric(item, "reference_quality_method", method)
            if psnr < float(self.config.get("min_reference_psnr", 24.0)):  # Flag low PSNR when it falls below the configured threshold.
                self.add_issue(item, "reference_low_psnr")
            if psnr < float(self.config.get("severe_reference_psnr", 20.0)):  # Flag severe reference differences when PSNR is very low.
                self.add_issue(item, "reference_severe_difference")
            if ssim < float(self.config.get("min_reference_ssim", 0.65)):  # Flag low SSIM when structural similarity is too low.
                self.add_issue(item, "reference_low_ssim")
        except Exception:
            self.add_issue(item, "reference_eval_failed")
        return item

    def _psnr(self, a: list[int], b: list[int]) -> float:
        """Compute peak signal-to-noise ratio from two pixel vectors.

        Business logic:
            1. Compute mean squared error between aligned pixels.
            2. Return a high constant when the images are effectively identical.
            3. Otherwise return PSNR derived from the root mean squared error.

        Args:
                a (list[int]): First pixel vector.
                b (list[int]): Second pixel vector.

        Returns:
            float: Peak signal-to-noise ratio.

        Examples:
            >>> _psnr
            _psnr
        """
        if not a or not b:  # Return a neutral failure score when either image array is empty.
            return 0.0
        mse = mean((x - y) ** 2 for x, y in zip(a, b))
        if mse <= 1e-9:  # Treat near-zero error as an effectively identical image.
            return 99.0
        return 20.0 * math.log10(255.0 / math.sqrt(mse))

    def _simple_ssim(self, a: list[int], b: list[int]) -> float:
        """Compute a simplified SSIM score from two pixel vectors.

        Business logic:
            1. Compute means, variances, and covariance from aligned pixels.
            2. Apply the simplified SSIM formula.
            3. Clamp the result into the valid similarity range.

        Args:
                a (list[int]): First pixel vector.
                b (list[int]): Second pixel vector.

        Returns:
            float: Simplified SSIM score.

        Examples:
            >>> _simple_ssim
            _simple_ssim
        """
        if not a or not b:  # Return a neutral failure score when either image array is empty.
            return 0.0
        mean_a = mean(a)
        mean_b = mean(b)
        var_a = mean((x - mean_a) ** 2 for x in a)
        var_b = mean((y - mean_b) ** 2 for y in b)
        cov = mean((x - mean_a) * (y - mean_b) for x, y in zip(a, b))
        c1 = 6.5025
        c2 = 58.5225
        numerator = (2 * mean_a * mean_b + c1) * (2 * cov + c2)
        denominator = (mean_a**2 + mean_b**2 + c1) * (var_a + var_b + c2)
        return max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0

class SubjectCompletenessOperator(ImageOperator):
    operator_name: str = "subject_completeness"  # Operator identifier used by workflow configs and the registry.

    def process(self, item: dict) -> dict:
        """Estimate whether the visual subject is complete and centered.

        Business logic:
            1. Analyze center-region entropy, edge density, and variance.
            2. Compare center strength against border edge activity.
            3. Add issues for missing, weak, or crop-risk subjects.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or Image is None or np is None or "decode_failed" in issues or "image_missing" in issues:  # Skip subject checks when required image capabilities are unavailable.
            return item
        path = self.image_path(item)
        try:
            with Image.open(path) as image:
                gray = image.convert("L").resize((256, 256))
            arr = np.array(gray)
            center = arr[64:192, 64:192]
            border_parts = [
                arr[:32, :],
                arr[-32:, :],
                arr[:, :32],
                arr[:, -32:],
            ]
            center_entropy = image_entropy(center)
            center_edges = edge_density(center)
            center_std = float(center.std() / 255.0)
            border_edge = max(edge_density(part) for part in border_parts)
            center_score = min(1.0, center_entropy * 0.45 + center_edges * 2.2 + center_std * 1.2)
            crop_risk = min(1.0, border_edge * 4.0)
            self.set_metric(item, "subject_center_score", round(center_score, 4))
            self.set_metric(item, "subject_crop_risk", round(crop_risk, 4))
            if center_score < float(self.config.get("min_center_score", 0.10)):  # Flag missing subjects when center strength is too low.
                self.add_issue(item, "subject_missing")
            elif center_score < float(self.config.get("review_center_score", 0.18)):
                self.add_issue(item, "subject_weak")
            if crop_risk > float(self.config.get("max_crop_risk", 0.55)):  # Flag crop risk when border edge activity is too strong.
                self.add_issue(item, "subject_crop_risk")
        except Exception:
            self.add_issue(item, "subject_check_failed")
        return item

class VLMImageQualityOperator(ImageOperator):
    operator_name: str = "vlm_image_quality"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for VLM-based image quality checks.

        Business logic:
            1. Read client or model settings from operator config.
            2. Create a reusable vision client for processing.
            3. Keep setup side effects limited to client creation.

        Args:
                None: This hook does not take input parameters.

        Returns:
            None: The hook prepares runtime client state in place.

        Examples:
            >>> setup
            setup
        """
        self.client = OpenAICompatibleVisionClient(self.config.get("vlm", self.config))  # Reusable external client configured from operator settings.

    def process(self, item: dict) -> dict:
        """Evaluate image quality with a VLM or local fallback.

        Business logic:
            1. Use the API path when the VLM client is enabled, otherwise fall back locally.
            2. Record VLM quality metrics from the chosen evaluation path.
            3. Add quality issues according to action hints and configured score thresholds.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or "decode_failed" in issues or "image_missing" in issues:  # Skip VLM quality checks when the image is unreadable or missing.
            return item
        path = self.image_path(item)
        if self.client.is_enabled():  # Use the API path when the external model is fully configured.
            result, error = self._call_vlm(path)
            if error:  # Record fallback reasons when the API path fails.
                self.add_issue(item, "vlm_api_fallback")
                self.set_metric(item, "vlm_quality_error", error)
                result = self._local_quality(item)
                mode = "local_fallback"
            else:
                mode = "api"
        else:
            result = self._local_quality(item)
            mode = "local_fallback"
        score = bounded_float(result.get("image_quality_score", 1.0), 1.0)
        action_hint = str(result.get("action_hint", "keep"))
        reason = str(result.get("reason", ""))
        self.set_metric(item, "vlm_quality_mode", mode)
        self.set_metric(item, "vlm_image_quality_score", round(score, 4))
        self.set_metric(item, "vlm_action_hint", action_hint)
        self.set_metric(item, "vlm_quality_reason", reason[:300])
        if action_hint == "drop":  # Record an explicit drop hint from the vision model.
            self.add_issue(item, "vlm_drop_hint")
        elif action_hint == "review":
            self.add_issue(item, "vlm_review_hint")
        if score < float(self.config.get("min_vlm_score", 0.55)):  # Flag low quality when the score is below the configured minimum.
            self.add_issue(item, "vlm_low_quality")
        elif score < float(self.config.get("review_vlm_score", 0.72)):
            self.add_issue(item, "vlm_quality_review")
        return item

    def _call_vlm(self, path: Path) -> tuple[dict[str, Any], str]:
        """Call the vision model for image quality evaluation.

        Business logic:
            1. Assemble the outbound quality prompt.
            2. Send the request and read the JSON response.
            3. Return the structured result and any error message.

        Args:
                path (Path): File path.

        Returns:
            tuple[dict[str, Any], str]: Structured result and error string.

        Examples:
            >>> _call_vlm
            _call_vlm
        """
        prompt = (
            "Evaluate this image for a multimodal data denoising tool. Return strict JSON only with keys: "
            "image_quality_score(0-1), action_hint(keep/review/drop), has_watermark, has_qr, has_logo, "
            "subject_present, cropped, unsafe, reason. Do not describe unrelated details."
        )
        return self.client.chat_json(path, prompt)

    def _local_quality(self, item: dict) -> dict[str, Any]:
        """Estimate image quality from local metrics and issues.

        Business logic:
            1. Fuse issue tags into a conservative quality score.
            2. Derive an action hint from the resulting score.
            3. Return the local image-quality estimate.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Local image-quality estimate.

        Examples:
            >>> _local_quality
            _local_quality
        """
        issues = set(item.get("issues", []))
        score = 1.0
        if "safety_risk" in issues or "qrcode_detected" in issues or "subject_missing" in issues:  # Treat safety risks, QR codes, and missing subjects as high-risk conditions.
            score = 0.2
        elif "reference_severe_difference" in issues:
            score = 0.35
        elif "watermark_detected" in issues or "logo_detected" in issues or "subject_weak" in issues:
            score = 0.66
        elif "blur" in issues or "under_exposure" in issues or "over_exposure" in issues:
            score = 0.74
        action_hint = "keep"
        if score < 0.55:  # Map low local scores to a drop action.
            action_hint = "drop"
        elif score < 0.75:
            action_hint = "review"
        return {"image_quality_score": score, "action_hint": action_hint, "reason": "local issue fusion"}
