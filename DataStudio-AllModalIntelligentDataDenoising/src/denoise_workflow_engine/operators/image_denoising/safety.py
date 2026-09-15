from typing import Any
from denoise_workflow_engine.utilities.image.base import *  # noqa: F403

class ImageSafetyOperator(ImageOperator):
    operator_name: str = "image_safety"  # Operator identifier used by workflow configs and the registry.

    def setup(self) -> None:
        """Initialize external dependencies for image safety evaluation.

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
        """Evaluate safety risk for one image sample.

        Business logic:
            1. Use the API path when the VLM client is enabled, otherwise fall back locally.
            2. Record safety metrics from the chosen evaluation path.
            3. Add a safety-risk issue when confidence exceeds the configured threshold.

        Args:
                item (dict): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        issues = item.get("issues", [])
        if self.should_skip(item) or "decode_failed" in issues or "image_missing" in issues:  # Skip safety checks when the image is unreadable or missing.
            return item
        path = self.image_path(item)
        if self.client.is_enabled():  # Use the API path when the external model is fully configured.
            result, error = self._call_vlm(path)
            if error:  # Record fallback reasons when the API path fails.
                self.add_issue(item, "vlm_api_fallback")
                self.set_metric(item, "safety_vlm_error", error)
                result = self._local_safety(path)
                mode = "local_fallback"
            else:
                mode = "api"
        else:
            result = self._local_safety(path)
            mode = "local_fallback"
        safe = bool(result.get("safe", True))
        confidence = bounded_float(result.get("confidence", 0.0))
        risk_category = str(result.get("risk_category", "none"))
        self.set_metric(item, "safety_mode", mode)
        self.set_metric(item, "safety_safe", safe)
        self.set_metric(item, "safety_confidence", round(confidence, 4))
        self.set_metric(item, "safety_risk_category", risk_category)
        if not safe and confidence >= float(self.config.get("min_risk_confidence", 0.45)):  # Add a risk issue only when confidence exceeds the configured threshold.
            self.add_issue(item, "safety_risk")
        return item

    def _call_vlm(self, path: Path) -> tuple[dict[str, Any], str]:
        """Call the vision model for safety assessment.

        Business logic:
            1. Assemble the outbound safety prompt.
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
            "Assess image safety for a data-cleaning pipeline. Return strict JSON only with keys: "
            "safe(boolean), risk_category(string), confidence(0-1), reason(string). "
            "Risk categories include porn, violence, blood, hate, illegal, spam, none."
        )
        return self.client.chat_json(path, prompt)

    def _local_safety(self, path: Path) -> dict[str, Any]:
        """Estimate image safety risk with local visual features.

        Business logic:
            1. Read the image into a normalized RGB array.
            2. Measure warning-red regions as a cheap local safety heuristic.
            3. Return a structured local safety assessment result.

        Args:
                path (Path): File path.

        Returns:
            dict[str, Any]: Local safety assessment result.

        Examples:
            >>> _local_safety
            _local_safety
        """
        if Image is None or np is None:  # Local safety heuristics are unavailable without Pillow and NumPy.
            return {"safe": True, "risk_category": "none", "confidence": 0.0}
        try:
            with Image.open(path) as image:
                rgb = image.convert("RGB").resize((256, 256))
            arr = np.array(rgb).astype("float32")
            red = arr[:, :, 0]
            green = arr[:, :, 1]
            blue = arr[:, :, 2]
            warning_red_ratio = float(((red > 170) & (green < 80) & (blue < 80)).mean())
            if warning_red_ratio > float(self.config.get("max_warning_red_ratio", 0.10)):  # Flag warning-marker-like red overlays when the ratio exceeds threshold.
                return {"safe": False, "risk_category": "synthetic_warning_marker", "confidence": 0.75}
        except (OSError, ValueError):
            return {"safe": True, "risk_category": "none", "confidence": 0.0}
        return {"safe": True, "risk_category": "none", "confidence": 0.7}
