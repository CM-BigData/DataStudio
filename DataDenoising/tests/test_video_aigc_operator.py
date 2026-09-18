import json
from pathlib import Path
import shutil

from denoise_workflow_engine.operators.video_denoising.aigc import VideoAIGCDetectOperator
from denoise_workflow_engine.runtime.loader import load_workflow_config
from denoise_workflow_engine.runtime.registry import build_default_registry
from denoise_workflow_engine.runtime.executor import WorkflowExecutor


def _setup_operator(config: dict | None = None) -> VideoAIGCDetectOperator:
    """Create and initialize the video AIGC operator for tests.

    Business logic:
        1. Build the operator instance.
        2. Call setup to initialize the detector backend.
        3. Return an operator object that can be executed directly.

    Args:
        config (dict | None): Operator configuration.

    Returns:
        VideoAIGCDetectOperator: Initialized operator.

    Examples:
        >>> isinstance(_setup_operator({}), VideoAIGCDetectOperator)
        True
    """
    operator = VideoAIGCDetectOperator(config or {})
    operator.setup()
    return operator


def test_video_denoise_registers_normally() -> None:
    """Verify that the default registry exposes the end-to-end video denoise operator.

    Business logic:
        1. Build the default registry.
        2. Create the end-to-end operator by operator_name.
        3. Assert that the old internal stage is no longer publicly registered.

    Args:
        None.

    Returns:
        None: The test returns no business value when it passes.

    Examples:
        >>> callable(test_video_denoise_registers_normally)
        True
    """
    registry = build_default_registry()
    assert registry.create("video_denoise", {})
    try:
        registry.create("video_aigc_detect", {})
    except KeyError:
        pass
    else:
        raise AssertionError("internal video AIGC stage should not be registered")


def test_video_aigc_threshold_marks_suspected_video() -> None:
    """Verify that scores above the threshold produce the dedicated AIGC issue.

    Business logic:
        1. Build a sample with obvious AI keywords and a single visual description.
        2. Run the fallback detector.
        3. Assert that the score, boolean marker, and issue are all present.

    Args:
        None.

    Returns:
        None: The test returns no business value when it passes.

    Examples:
        >>> callable(test_video_aigc_threshold_marks_suspected_video)
        True
    """
    operator = _setup_operator({"video_aigc_threshold": 0.55})
    item = {
        "id": "suspected",
        "modality": "video",
        "payload": {"video_path": "input/videos/local_real_smoke/video_freeze.mp4"},
        "intermediate": {
            "vlm_frame_descriptions": ["AI generated avatar speaks in a studio", "AI generated avatar speaks in a studio"],
            "subtitle_text": "AI generated avatar explains the product.",
            "asr_text": "This AI generated presenter explains the product.",
            "visual_keywords": ["ai generated", "avatar", "digital human"],
        },
        "metrics": {"keyframe_count": 4, "freeze_frame_ratio": 1.0, "video_qr_detected": False},
        "issues": [],
        "operator_trace": [],
    }

    processed = operator.process(item)

    assert processed["metrics"]["suspected_video_aigc"] is True
    assert processed["metrics"]["video_aigc_backend"] == "fallback"
    assert processed["metrics"]["video_aigc_score"] >= 0.55
    assert "suspected_video_aigc" in processed["issues"]


def test_video_aigc_fallback_prefers_natural_signals() -> None:
    """Verify that fallback heuristics keep normal real-shot signals below the threshold.

    Business logic:
        1. Build a sample with real-shot descriptions, subtitles, and ASR text.
        2. Run the fallback detector.
        3. Assert that the backend is fallback and does not misclassify the sample as AIGC.

    Args:
        None.

    Returns:
        None: The test returns no business value when it passes.

    Examples:
        >>> callable(test_video_aigc_fallback_prefers_natural_signals)
        True
    """
    operator = _setup_operator({"video_aigc_threshold": 0.55})
    item = {
        "id": "real",
        "modality": "video",
        "payload": {"video_path": "input/videos/local_real_smoke/video_clean.mp4"},
        "intermediate": {
            "vlm_frame_descriptions": ["Handheld outdoor footage of a bird on a branch"],
            "subtitle_text": "实拍短视频，画面展示一只翠鸟停在树枝上。",
            "asr_text": "这是今天在公园拍到的翠鸟视频。",
            "visual_keywords": ["bird", "branch", "outdoor", "handheld"],
        },
        "metrics": {"keyframe_count": 4, "freeze_frame_ratio": 0.0, "video_qr_detected": False},
        "issues": [],
        "operator_trace": [],
    }

    processed = operator.process(item)

    assert processed["metrics"]["video_aigc_backend"] == "fallback"
    assert processed["metrics"]["suspected_video_aigc"] is False
    assert processed["metrics"]["video_aigc_score"] < 0.55
    assert "suspected_video_aigc" not in processed["issues"]


def test_video_aigc_workflow_runs_with_real_samples() -> None:
    """Verify that the standalone video AIGC workflow runs on the reproducible video subset.

    Business logic:
        1. Load the standalone video AIGC workflow.
        2. Run the sample set with real-shot, short-video, and weakly labeled suspected AIGC samples.
        3. Assert that true AIGC samples go to review while public real videos stay in keep.

    Args:
        None.

    Returns:
        None: The test returns no business value when it passes.

    Examples:
        >>> callable(test_video_aigc_workflow_runs_with_real_samples)
        True
    """
    workflow_path = Path("workflows/video_aigc_detect_smoke.yaml")
    run_dir = Path("outputs/video_aigc_detect_smoke")
    shutil.rmtree(run_dir, ignore_errors=True)
    config = load_workflow_config(workflow_path)
    registry = build_default_registry(config.get("custom_operators", []), base_dir=workflow_path.resolve().parent)
    summary = WorkflowExecutor(config=config, registry=registry, base_dir=workflow_path.resolve().parent).run()

    clean_rows = [
        json.loads(line)
        for line in (run_dir / "clean.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    review_rows = [
        json.loads(line)
        for line in (run_dir / "review.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    clean_ids = {row["id"] for row in clean_rows}
    review_ids = {row["id"] for row in review_rows}

    assert summary["total_count"] == 3
    assert "video_real_mov_bbb_001" in clean_ids
    assert "video_real_sintel_trailer_001" in clean_ids
    assert "video_aigc_kling_001" in review_ids
