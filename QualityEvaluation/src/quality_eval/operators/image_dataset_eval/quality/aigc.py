from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quality_eval.utilities.image.shared import *  # noqa: F403


@dataclass
class AigcDetectionResult:
    """Represent one AIGC detection result.

    Business logic:
        1. Carry the score, boolean decision, backend name, and reason text.
        2. Let model-backed and fallback detectors share one stable return type.
        3. Provide a direct structure for workflow metrics and issue writes.

    Args:
        score (float): AIGC probability score in the range [0, 1].
        suspected (bool): Whether the score crosses the configured threshold.
        backend (str): Backend name that produced this result.
        reason (str): Human-readable explanation of the detection outcome.

    Returns:
        None: The dataclass stores fields only.

    Examples:
        >>> AigcDetectionResult(0.9, True, "fallback", "high score").suspected
        True
    """

    score: float  # Sample-level AIGC score written to `metrics.aigc_score`.
    suspected: bool  # Boolean threshold decision written to `metrics.suspected_aigc`.
    backend: str  # Detector backend name such as `huggingface` or `fallback`.
    reason: str  # Backend-specific explanation or fallback feature summary.


class AigcDetector(Protocol):
    def detect(self, image: Image.Image, threshold: float) -> AigcDetectionResult:
        """Run AIGC detection for one image.

        Business logic:
            1. Accept one loaded Pillow image.
            2. Produce an AIGC score and compare it with the threshold.
            3. Return the normalized detection result structure.

        Args:
            image (Image.Image): Input image.
            threshold (float): Suspicion threshold.

        Returns:
            AigcDetectionResult: Normalized detection result.

        Examples:
            >>> hasattr(AigcDetector, "detect")
            True
        """


class HuggingFaceAigcDetector:
    """AIGC detector backed by a Hugging Face pipeline."""

    def __init__(self, model_name: str) -> None:
        """Initialize the Hugging Face AIGC detector.

        Business logic:
            1. Import `transformers` lazily so missing dependencies fail only here.
            2. Build an `image-classification` pipeline from the configured model.
            3. Cache the pipeline on the instance for repeated inference.

        Args:
            model_name (str): Model name or local model path.

        Returns:
            None: The initializer stores the pipeline on the instance.

        Examples:
            >>> callable(HuggingFaceAigcDetector.__init__)
            True
        """
        try:
            from transformers import pipeline
        except ImportError as exc:
            raise RuntimeError("transformers is not installed") from exc

        self._pipeline = pipeline("image-classification", model=model_name)

    def detect(self, image: Image.Image, threshold: float) -> AigcDetectionResult:
        """Run model inference through the Hugging Face pipeline.

        Business logic:
            1. Invoke the image-classification pipeline on the input image.
            2. Prefer scores from artificial or AI-like labels when present.
            3. Normalize the prediction into the shared detection result type.

        Args:
            image (Image.Image): Input image.
            threshold (float): Suspicion threshold.

        Returns:
            AigcDetectionResult: Model-backed detection result.

        Examples:
            >>> callable(HuggingFaceAigcDetector.detect)
            True
        """
        predictions = self._pipeline(image)
        score = 0.0
        label = "unknown"
        for prediction in predictions:  # Prefer explicit AI-generation labels when the model provides them.
            prediction_label = str(prediction.get("label", "")).lower()
            if prediction_label in {"artificial", "ai", "fake", "generated"}:  # Use the direct AI-like label score.
                score = float(prediction.get("score", 0.0))
                label = prediction_label
                break
            if prediction_label in {"real", "human"}:  # Convert real-image confidence into the inverse AIGC score.
                score = 1.0 - float(prediction.get("score", 0.0))
                label = prediction_label

        suspected = score >= threshold

        return AigcDetectionResult(
            score=round(max(0.0, min(1.0, score)), 6),
            suspected=suspected,
            backend="huggingface",
            reason=f"model_label={label}",
        )


class HeuristicAigcDetector:
    """Stable heuristic fallback detector for AIGC checks."""

    def detect(self, image: Image.Image, threshold: float) -> AigcDetectionResult:
        """Run heuristic AIGC detection from texture and color features.

        Business logic:
            1. Compute grayscale statistics, sharpness, palette dominance, and saturation.
            2. Combine lightweight heuristics into a stable score in the range [0, 1].
            3. Return reproducible fallback output so the workflow can run without a model.

        Args:
            image (Image.Image): Input image.
            threshold (float): Suspicion threshold.

        Returns:
            AigcDetectionResult: Heuristic fallback result.

        Examples:
            >>> img = Image.new("RGB", (32, 32), "white")
            >>> HeuristicAigcDetector().detect(img, 0.28).backend
            'fallback'
        """
        rgb = image.convert("RGB").resize((256, 256))
        hsv = rgb.convert("HSV")
        stats = _grayscale_statistics(rgb)
        sharpness = float(_sharpness(rgb))
        hsv_values = list(hsv.getdata())
        saturation_mean = sum(pixel[1] for pixel in hsv_values) / max(1, len(hsv_values))
        value_mean = sum(pixel[2] for pixel in hsv_values) / max(1, len(hsv_values))
        quantized = rgb.quantize(colors=32)
        color_histogram = quantized.histogram()
        dominant_palette_ratio = max(color_histogram) / max(1, sum(color_histogram))
        occupied_palette_bins = sum(1 for count in color_histogram if count > 0)

        smoothness_score = max(0.0, 1.0 - min(float(stats["std_intensity"]) / 64.0, 1.0))
        dominance_score = min(1.0, dominant_palette_ratio * 2.4)
        saturation_score = min(1.0, saturation_mean / 180.0)
        sharpness_mid_score = max(0.0, 1.0 - min(abs(sharpness - 24.0) / 24.0, 1.0))
        palette_compact_score = max(0.0, 1.0 - min(occupied_palette_bins / 32.0, 1.0))
        brightness_balance_score = 1.0 - min(abs((value_mean / 255.0) - 0.58) / 0.58, 1.0)

        score = (
            smoothness_score * 0.24
            + dominance_score * 0.22
            + saturation_score * 0.18
            + sharpness_mid_score * 0.18
            + palette_compact_score * 0.10
            + brightness_balance_score * 0.08
        )
        score = round(max(0.0, min(1.0, score)), 6)
        suspected = score >= threshold
        reason = (
            "fallback:"
            f"smooth={smoothness_score:.3f},dominant={dominance_score:.3f},"
            f"saturation={saturation_score:.3f},sharp_mid={sharpness_mid_score:.3f},"
            f"palette={palette_compact_score:.3f}"
        )
        return AigcDetectionResult(score=score, suspected=suspected, backend="fallback", reason=reason)


class ImageAigcEvalOperator(BaseOperator):
    operator_name: str = "image_aigc_eval"  # Stable registry name used by workflow steps.

    def __init__(self, config: dict[str, Any]) -> None:
        """Initialize the image AIGC evaluation operator.

        Business logic:
            1. Read the threshold, model name, and detector backend preference.
            2. Build the detector with the `auto -> huggingface -> fallback` strategy.
            3. Fall back to the stable heuristic detector when the model path is unavailable.

        Args:
            config (dict[str, Any]): Workflow-injected operator config.

        Returns:
            None: The initializer stores the detector and resolved backend.

        Examples:
            >>> op = ImageAigcEvalOperator({"rules": {}})
            >>> op.operator_name
            'image_aigc_eval'
        """
        super().__init__(config)
        self.threshold = float(self.rules.get("aigc_threshold", 0.28))  # Use 0.28 by default because it is steadier for the current fallback validation set.
        self.model_name = str(self.rules.get("aigc_model_name", "haywoodsloan/ai-image-detector-deploy"))  # Accept either a local model path or a Hugging Face model id.
        self.backend_preference = str(self.rules.get("aigc_detector_backend", "auto")).lower()  # Support `auto`, `huggingface`, and `fallback`.
        self.detector, self.actual_backend = self._build_detector()

    def _build_detector(self) -> tuple[AigcDetector, str]:
        """Build the detector from the configured backend preference.

        Business logic:
            1. Return the heuristic detector immediately for explicit `fallback`.
            2. Require successful model initialization for explicit `huggingface`.
            3. Try the model first and then fall back for `auto`.

        Args:
            None.

        Returns:
            tuple[AigcDetector, str]: Detector instance and resolved backend name.

        Examples:
            >>> op = ImageAigcEvalOperator({"rules": {"aigc_detector_backend": "fallback"}})
            >>> op.actual_backend
            'fallback'
        """
        if self.backend_preference == "fallback":  # Skip model dependencies when the workflow explicitly selects fallback.
            return HeuristicAigcDetector(), "fallback"
        if self.backend_preference == "huggingface":  # Surface initialization failures when the workflow explicitly requires the model backend.
            return HuggingFaceAigcDetector(self.model_name), "huggingface"
        try:
            return HuggingFaceAigcDetector(self.model_name), "huggingface"
        except Exception:
            return HeuristicAigcDetector(), "fallback"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Run AIGC evaluation for one image sample.

        Business logic:
            1. Read `payload.image_path` and verify that the file exists.
            2. Load the image and obtain an AIGC score from the detector.
            3. Write `aigc_score`, `suspected_aigc`, and backend metrics back to the sample.
            4. Append `suspected_aigc_image` when the threshold is crossed.

        Args:
            item (dict[str, Any]): Image sample.

        Returns:
            dict[str, Any]: Sample updated with AIGC metrics and issues.

        Examples:
            >>> sample = {"payload": {}, "metrics": {}, "issues": []}
            >>> ImageAigcEvalOperator({"rules": {}}).process(sample)["metrics"]["aigc_score"] is None
            True
        """
        image_path = item.get("payload", {}).get("image_path")
        if not image_path:  # Write empty metrics only and let upstream decode checks own the path-related issue.
            self.metric(item, "aigc_score", None)
            self.metric(item, "suspected_aigc", False)
            self.metric(item, "aigc_detector_backend", self.actual_backend)
            self.metric(item, "aigc_detection_reason", "missing_image_path")
            return item
        if not Path(image_path).exists():  # Keep missing-file behavior aligned with the other image evaluation operators.
            self.metric(item, "aigc_score", None)
            self.metric(item, "suspected_aigc", False)
            self.metric(item, "aigc_detector_backend", self.actual_backend)
            self.metric(item, "aigc_detection_reason", "image_not_found")
            return item
        try:
            with Image.open(image_path) as image:
                result = self.detector.detect(image, self.threshold)
        except Exception as exc:
            self.metric(item, "aigc_score", None)
            self.metric(item, "suspected_aigc", False)
            self.metric(item, "aigc_detector_backend", self.actual_backend)
            self.metric(item, "aigc_detection_reason", f"detector_error:{exc}")
            return item

        self.metric(item, "aigc_score", result.score)
        self.metric(item, "suspected_aigc", result.suspected)
        self.metric(item, "aigc_detector_backend", result.backend)
        self.metric(item, "aigc_detection_reason", result.reason)
        if result.suspected:  # Append the issue only when the standalone AIGC threshold is crossed.
            self.add_issue(item, "suspected_aigc_image")
        return item
