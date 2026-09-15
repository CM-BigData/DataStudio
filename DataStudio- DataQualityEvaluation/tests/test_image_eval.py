from pathlib import Path
import json

import pytest
from PIL import Image

from quality_eval.cli import main
from quality_eval.operators.image_dataset_eval.quality.blank import ImageBlankEvalOperator
from quality_eval.operators.image_dataset_eval.quality.cross_modal import ImageTextConsistencyEvalOperator
from quality_eval.operators.image_dataset_eval.quality.lossless import ImageLosslessEvalOperator
from quality_eval.utilities.image.shared import _average_hash


def test_image_text_consistency_remote_model_requires_immutable_revision() -> None:
    operator = ImageTextConsistencyEvalOperator(
        {
            "rules": {
                "image_text_consistency_model_name": "organization/model",
            }
        }
    )

    with pytest.raises(RuntimeError, match="immutable model revision"):
        operator._load_model()


def test_average_hash_uses_sha256_content_fingerprint() -> None:
    """Verify that image content fingerprints are stable SHA-256 digests.

    Business logic:
        1. Build small in-memory images with controlled size and pixels.
        2. Confirm identical image content produces the same digest.
        3. Confirm pixel and size changes produce different digests.
        4. Confirm the digest length matches a SHA-256 hexadecimal fingerprint.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_average_hash_uses_sha256_content_fingerprint)
        True
    """
    white_1x1 = Image.new("RGB", (1, 1), "white")
    same_white_1x1 = Image.new("RGB", (1, 1), "white")
    black_1x1 = Image.new("RGB", (1, 1), "black")
    white_2x1 = Image.new("RGB", (2, 1), "white")

    digest = _average_hash(white_1x1)

    assert len(digest) == 64
    assert digest == _average_hash(same_white_1x1)
    assert digest != _average_hash(black_1x1)
    assert digest != _average_hash(white_2x1)


def test_image_workflow_outputs_expected_issues() -> None:
    """Verify that the image workflow emits the expected issue codes.

    Business logic:
        1. Run the full evaluation workflow on the sample image dataset.
        2. Read the output JSONL file.
        3. Assert that path, format, size, blur, annotation, and duplication issues are detected.

    Args:
        None.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_image_workflow_outputs_expected_issues)
        True
    """
    output_dir = "test_runs/pytest_image"
    assert main(["run", "-c", "workflows/image_dataset_eval.yaml", "--task-id", "pytest_image", "--output-dir", output_dir]) == 0
    result_path = Path(output_dir) / "image_eval_result.jsonl"
    content = result_path.read_text(encoding="utf-8")
    for issue in [  # The sample image dataset intentionally covers these issue codes.
        "missing_image_path",
        "image_not_found",
        "image_unreadable",
        "image_broken",
        "unsupported_format",
        "width_too_small",
        "height_too_small",
        "aspect_ratio_abnormal",
        "blurred_image",
        "missing_label",
        "duplicate_image",
        "bbox_out_of_bounds",
    ]:
        assert issue in content


def test_validate_image_config() -> None:
    """Verify that the image workflow configuration passes validation.

    Business logic:
        1. Run the `validate-config` subcommand.
        2. Load the sample image workflow.
        3. Confirm that the config structure, operators, and input paths are valid.

    Args:
        None.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_validate_image_config)
        True
    """
    assert main(["validate-config", "-c", "workflows/image_dataset_eval.yaml"]) == 0


def test_image_blank_eval_detects_expected_cases() -> None:
    """Verify blank-image detection for normal, white, black, and near-solid cases.

    Business logic:
        1. Build minimal samples for white, black, near-solid, and normal cases.
        2. Inject grayscale statistics aligned with `image_decode_eval` to avoid duplicate file I/O setup.
        3. Run `image_blank_eval` and assert that metrics and issues match expectations.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_image_blank_eval_detects_expected_cases)
        True
    """
    operator = ImageBlankEvalOperator({"rules": {}})
    cases = [
        (
            "white",
            {"mean_intensity": 255, "std_intensity": 0, "dynamic_range": 0, "dominant_ratio": 1.0, "min_intensity": 255, "max_intensity": 255},
            {"pure_white_image", "blank_content_image"},
        ),
        (
            "black",
            {"mean_intensity": 0, "std_intensity": 0, "dynamic_range": 0, "dominant_ratio": 1.0, "min_intensity": 0, "max_intensity": 0},
            {"pure_black_image", "blank_content_image"},
        ),
        (
            "near_solid",
            {"mean_intensity": 150.2, "std_intensity": 2.64, "dynamic_range": 16, "dominant_ratio": 0.1385, "min_intensity": 143, "max_intensity": 159},
            {"near_solid_color_image"},
        ),
        (
            "normal",
            {"mean_intensity": 73.45, "std_intensity": 37.59, "dynamic_range": 240, "dominant_ratio": 0.0193, "min_intensity": 7, "max_intensity": 247},
            set(),
        ),
    ]
    for sample_id, stats, expected_issues in cases:
        sample = {"id": sample_id, "intermediate": {"grayscale_stats": stats}, "metrics": {"readable": True}, "issues": []}
        result = operator.process(sample)
        assert set(result["issues"]) == expected_issues
        assert "blank_content_score" in result["metrics"]
        assert result["metrics"]["blank_image_detected"] is bool(expected_issues)


def test_image_lossless_eval_detects_corrupted_sample() -> None:
    """Verify the lossless-integrity check detects corrupted image files.

    Business logic:
        1. Build one clean sample and one corrupted sample from public example data.
        2. Run the lossless-integrity operator directly on both samples.
        3. Assert that the corrupted sample gets `image_broken` while the clean sample does not.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_image_lossless_eval_detects_corrupted_sample)
        True
    """
    operator = ImageLosslessEvalOperator({"rules": {}})
    clean_sample = {
        "payload": {"image_path": "example_data/image_dataset/img_good.jpg"},
        "metrics": {},
        "issues": [],
    }
    broken_sample = {
        "payload": {"image_path": "example_data/image_dataset/corrupted.jpg"},
        "metrics": {},
        "issues": [],
    }

    clean_result = operator.process(clean_sample)
    broken_result = operator.process(broken_sample)

    assert clean_result["metrics"]["image_lossless_ok"] is True
    assert "image_broken" not in clean_result["issues"]
    assert broken_result["metrics"]["image_lossless_ok"] is False
    assert "image_broken" in broken_result["issues"]


def test_validate_image_text_consistency_config() -> None:
    """Verify that the image-text consistency workflow configuration passes validation.

    Business logic:
        1. Run the `validate-config` subcommand.
        2. Load the image-text consistency workflow.
        3. Confirm that the workflow and its public sample input are valid.

    Args:
        None.

    Returns:
        None: The test does not return a business value.

    Examples:
        >>> callable(test_validate_image_text_consistency_config)
        True
    """
    assert main(["validate-config", "-c", "workflows/image_text_consistency_eval.yaml"]) == 0


def test_image_blank_workflow_with_real_samples() -> None:
    """Verify the blank-image workflow on real public image samples.

    Business logic:
        1. Run the `image_blank_eval` workflow on the real public sample subset.
        2. Read the output JSONL and build an index by sample id.
        3. Assert that the outputs match expectations for real photos, blank scans, near-blank crops, and solid-background crops.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_image_blank_workflow_with_real_samples)
        True
    """
    output_dir = "test_runs/pytest_image_blank_real"
    assert main(["run", "-c", "workflows/image_blank_eval.yaml", "--task-id", "pytest_image_blank_real", "--output-dir", output_dir]) == 0
    result_path = Path(output_dir) / "image_blank_eval_result.jsonl"
    rows = [json.loads(line) for line in result_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_id = {row["sample_id"]: row for row in rows}

    assert by_id["real_photo_cat"]["issues"] == []
    assert "blank_content_image" in by_id["scan_blank_page"]["issues"]
    assert "blank_content_image" in by_id["scan_blank_page_crop"]["issues"]
    assert "near_solid_color_image" in by_id["white_wall_background_crop"]["issues"]
    assert by_id["snow_field_near_blank"]["issues"] == []
