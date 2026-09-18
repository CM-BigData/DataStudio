from pathlib import Path
import json

from quality_eval.cli import main
from quality_eval.operators.image_dataset_eval.quality.aigc import AigcDetectionResult, ImageAigcEvalOperator
from quality_eval.runtime.registry import registry


class _StubDetector:
    def __init__(self, score: float, backend: str = "stub") -> None:
        """Build a detector stub for tests.

        Business logic:
            1. Store one fixed score and backend name.
            2. Remove dependence on real models or fallback heuristics in threshold tests.
            3. Keep assertions focused on operator behavior rather than detector internals.

        Args:
            score (float): Fixed score returned by the stub.
            backend (str, optional): Fixed backend name. Defaults to `stub`.

        Returns:
            None: The initializer stores the stub state.

        Examples:
            >>> _StubDetector(0.5).backend
            'stub'
        """
        self.score = score  # Fixed score used to control the suspected-AIGC branch explicitly in tests.
        self.backend = backend  # Fixed backend name used to assert metric writes.

    def detect(self, image: object, threshold: float) -> AigcDetectionResult:
        """Return one fixed detection result.

        Business logic:
            1. Ignore the actual image object.
            2. Compare the fixed score against the threshold.
            3. Return the shared detection structure used by real detectors.

        Args:
            image (object): Placeholder image object.
            threshold (float): Threshold value.

        Returns:
            AigcDetectionResult: Fixed detection result.

        Examples:
            >>> _StubDetector(0.8).detect(None, 0.28).suspected
            True
        """
        return AigcDetectionResult(
            score=self.score,
            suspected=self.score >= threshold,
            backend=self.backend,
            reason=f"stub_score={self.score}",
        )


def test_image_aigc_eval_threshold_logic() -> None:
    """Verify threshold behavior in the image AIGC operator.

    Business logic:
        1. Reuse the same real image input with low-score and high-score stub detectors.
        2. Confirm that scores below the threshold do not append the issue.
        3. Confirm that scores above the threshold write `suspected_aigc` and append the issue.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_image_aigc_eval_threshold_logic)
        True
    """
    image_path = "example_data/image_aigc_eval_sample/real_photo_cat.jpg"
    low_operator = ImageAigcEvalOperator({"rules": {"aigc_detector_backend": "fallback", "aigc_threshold": 0.6}})
    low_operator.detector = _StubDetector(0.31)
    low_result = low_operator.process({"payload": {"image_path": image_path}, "metrics": {}, "issues": []})
    assert low_result["metrics"]["aigc_score"] == 0.31
    assert low_result["metrics"]["suspected_aigc"] is False
    assert "suspected_aigc_image" not in low_result["issues"]

    high_operator = ImageAigcEvalOperator({"rules": {"aigc_detector_backend": "fallback", "aigc_threshold": 0.6}})
    high_operator.detector = _StubDetector(0.81)
    high_result = high_operator.process({"payload": {"image_path": image_path}, "metrics": {}, "issues": []})
    assert high_result["metrics"]["aigc_score"] == 0.81
    assert high_result["metrics"]["suspected_aigc"] is True
    assert "suspected_aigc_image" in high_result["issues"]


def test_image_aigc_eval_falls_back_when_model_unavailable(monkeypatch: object) -> None:
    """Verify fallback behavior when the model backend is unavailable.

    Business logic:
        1. Mock Hugging Face detector initialization to fail.
        2. Instantiate the operator in `auto` mode.
        3. Assert that the resolved backend becomes `fallback`.

    Args:
        monkeypatch: Pytest monkeypatch fixture.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_image_aigc_eval_falls_back_when_model_unavailable)
        True
    """
    from quality_eval.operators.image_dataset_eval.quality import aigc as aigc_module

    def _raise_init(self, model_name: str) -> None:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(aigc_module.HuggingFaceAigcDetector, "__init__", _raise_init)
    operator = ImageAigcEvalOperator({"rules": {"aigc_detector_backend": "auto"}})
    assert operator.actual_backend == "fallback"


def test_image_aigc_eval_is_internal_step_only() -> None:
    """Verify that the image AIGC check is internal-only.

    Business logic:
        1. Confirm the internal AIGC class can still be imported for direct tests.
        2. Confirm `image_aigc_eval` is not exposed as a workflow operator.
        3. Confirm the end-to-end image dataset operator remains the public entry.

    Args:
        None.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_image_aigc_eval_is_internal_step_only)
        True
    """
    assert ImageAigcEvalOperator.operator_name == "image_aigc_eval"
    try:
        registry.get("image_aigc_eval")
    except KeyError:
        pass
    else:
        raise AssertionError("internal AIGC step should not be registered as a workflow operator")
    assert registry.get("image_dataset_eval").operator_name == "image_dataset_eval"


def test_image_aigc_workflow_with_real_samples() -> None:
    """Verify that the real-sample AIGC workflow runs successfully.

    Business logic:
        1. Run the minimal workflow built from real public samples and weak-label samples.
        2. Read the JSONL output and index rows by sample id.
        3. Assert that real photos, illustration-like images, and weak-label samples all emit standalone AIGC metrics.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_image_aigc_workflow_with_real_samples)
        True
    """
    output_dir = "test_runs/pytest_image_aigc_real"
    assert main(["run", "-c", "workflows/image_aigc_eval.yaml", "--task-id", "pytest_image_aigc_real", "--output-dir", output_dir]) == 0
    result_path = Path(output_dir) / "image_aigc_eval_result.jsonl"
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["sample_id"]: row for row in rows}

    assert "aigc_score" in by_id["real_photo_cat"]["metrics"]
    assert by_id["real_photo_cat"]["metrics"]["aigc_detector_backend"] in {"fallback", "huggingface"}
    assert "aigc_score" in by_id["illustration_logo"]["metrics"]
    assert "aigc_score" in by_id["suspected_aigc_weak"]["metrics"]
    assert "suspected_aigc" in by_id["suspected_aigc_weak"]["metrics"]
