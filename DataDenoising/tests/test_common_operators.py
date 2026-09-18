import json
from pathlib import Path
import threading
import time
from typing import Any
from denoise_workflow_engine.operators.common.leakage import DataLeakageGuardOperator
from denoise_workflow_engine.operators.common.router import ModalityRouterOperator
from denoise_workflow_engine.operators.image_denoising.quality import ReferenceImageQualityOperator
from denoise_workflow_engine.operators.image_denoising.safety import ImageSafetyOperator
from denoise_workflow_engine.operators.image_denoising.signals import QRCodeDetectOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.ocr import OCRKeyFieldConsistencyOperator, OCRTextConsistencyOperator
from denoise_workflow_engine.operators.image_text_pair_denoising.similarity import (
    CLIPImageTextSimilarityOperator,
    ImageTextKeywordSimilarityOperator,
    VLMConsistencyOperator,
)
from denoise_workflow_engine.operators.text_denoising.language import LanguageDetectOperator
from denoise_workflow_engine.operators.text_denoising.normalize import EncodingDetectOperator
from denoise_workflow_engine.operators.text_denoising.text_sensitive import TextSensitiveDetectOperator
from denoise_workflow_engine.operators.text_denoising.safety import SensitiveContentFilter
from denoise_workflow_engine.operators.video_denoising.repair import VideoRepairOperator
from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.runtime.executor import WorkflowExecutor
from denoise_workflow_engine.runtime.registry import OperatorRegistry


def setup_operator(operator: Any) -> Any:
    """Initialize a test operator before execution.

    Business logic:
        1. Accept the test operator instance.
        2. Execute its `setup` hook.
        3. Return the initialized operator.

    Args:
            operator (Any): Test operator instance.

    Returns:
        Any: Initialized test operator.

    Examples:
        >>> setup_operator
        setup_operator
    """
    operator.setup()
    return operator


def test_registry_requires_snake_case() -> None:
    """Verify that the registry accepts only snake_case operator names.

    Business logic:
        1. Build valid and invalid test operator classes.
        2. Register the valid operator and confirm that class-name aliases are unavailable.
        3. Assert that registering the invalid operator raises an error.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_registry_requires_snake_case
        test_registry_requires_snake_case
    """

    class DemoOperator(BaseOperator):
        operator_name = "demo_operator"  # Valid snake_case registration name for the test operator.

    class BadOperator(BaseOperator):
        operator_name = "BadOperator"  # Invalid PascalCase registration name for the test operator.

    registry = OperatorRegistry()
    registry.register(DemoOperator)
    try:
        registry.create("DemoOperator", {})
    except KeyError:
        pass
    else:
        raise AssertionError("class alias should not be registered")
    try:
        registry.register(BadOperator)
    except ValueError:
        pass
    else:
        raise AssertionError("PascalCase operator_name should fail")


def test_default_registry_exposes_only_end_to_end_denoise_names() -> None:
    """Verify that the default registry exposes only end-to-end denoise operators.

    Business logic:
        1. Build the default operator registry.
        2. Create every end-to-end denoising operator.
        3. Assert that an internal stage name is unavailable.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_default_registry_exposes_only_end_to_end_denoise_names
        test_default_registry_exposes_only_end_to_end_denoise_names
    """
    from denoise_workflow_engine.runtime.registry import build_default_registry

    registry = build_default_registry()

    assert registry.create("text_denoise", {})
    assert registry.create("image_denoise", {})
    assert registry.create("image_text_pair_denoise", {})
    assert registry.create("video_denoise", {})
    assert registry.create("auto_denoise", {})
    try:
        registry.create("text_sensitive_detect", {})
    except KeyError:
        pass
    else:
        raise AssertionError("internal text-sensitive stage should not be registered")


def test_encoding_detect_handles_plain_unicode_text() -> None:
    """Verify that the encoding-detection operator handles ordinary Unicode text.

    Business logic:
        1. Build a sample containing ordinary Chinese text.
        2. Execute the `encoding_detect` operator.
        3. Assert that no `operator_failed` issue is added and encoding metrics are written.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_encoding_detect_handles_plain_unicode_text)
        True
    """
    operator = setup_operator(EncodingDetectOperator(config={}))
    item = {
        "id": "unicode_text",
        "payload": {"text": "This is a normal Chinese text sample and should pass encoding detection."},
        "issues": [],
        "metrics": {},
        "operator_trace": [],
    }

    processed = operator.process(item)

    assert "operator_failed" not in processed["issues"]
    assert processed["metrics"]["detected_encoding"] == "unicode_text"
    assert processed["metrics"]["mojibake_score"] == 0


def test_workflow_resume_skips_completed_samples(tmp_path: Path) -> None:
    """Verify that workflow resume skips samples already completed.

    Business logic:
        1. Create two text samples and a workflow containing only routing and quality-gate steps.
        2. Prewrite one completed sample into `clean.jsonl` and `checkpoint.json`.
        3. Enable resume mode and assert that the completed sample is not written again.

    Args:
            tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_workflow_resume_skips_completed_samples)
        True
    """
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        json.dumps({"id": "done", "payload": {"text": "completed text sample content is long enough"}})
        + "\n"
        + json.dumps({"id": "pending", "payload": {"text": "pending text sample content is long enough"}})
        + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "clean.jsonl").write_text(json.dumps({"id": "done", "action": "keep"}, ensure_ascii=False) + "\n", encoding="utf-8")
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"workflow_id": "resume_denoise", "completed_ids": ["done"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    config = {
        "workflow": {"id": "resume_denoise", "checkpoint": True, "resume": True},
        "input": {"type": "jsonl", "path": str(input_path)},
        "output": {"run_dir": str(run_dir), "clean_path": "clean.jsonl", "dropped_path": "dropped.jsonl", "review_path": "review.jsonl"},
        "steps": [{"id": "text_denoise", "operator": "text_denoise", "params": {"thresholds": {"keep_score": 0.0, "review_score": 0.0, "hard_fail_issues": []}}}],
    }
    from denoise_workflow_engine.runtime.registry import build_default_registry

    summary = WorkflowExecutor(config, build_default_registry()).run()

    rows = [line for line in (run_dir / "clean.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert sum('"id": "done"' in row or '"id":"done"' in row for row in rows) == 1
    assert any('"id": "pending"' in row or '"id":"pending"' in row for row in rows)
    assert summary["resume_enabled"] is True
    assert summary["skipped_count"] == 1
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert summary["input_total_count"] == 2
    assert summary["historical_completed_count"] == 1
    assert summary["newly_processed_count"] == 1
    assert summary["current_completed_count"] == 2
    assert summary["pending_count"] == 0
    assert "| total_count | 2 |" in report
    assert "| current_run_count | 1 |" in report
    assert "| historical_completed_count | 1 |" in report
    assert "| newly_processed_count | 1 |" in report
    assert "| current_completed_count | 2 |" in report


def test_workflow_resume_report_keeps_input_total_when_all_samples_completed(tmp_path: Path) -> None:
    """Verify all-skipped resume reports keep input-total and current-run counts separate."""
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        json.dumps({"id": "done_1", "payload": {"text": "done text sample one is long enough"}})
        + "\n"
        + json.dumps({"id": "done_2", "payload": {"text": "done text sample two is long enough"}})
        + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "clean.jsonl").write_text(
        json.dumps({"id": "done_1", "action": "keep"}, ensure_ascii=False)
        + "\n"
        + json.dumps({"id": "done_2", "action": "keep"}, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "checkpoint.json").write_text(
        json.dumps({"workflow_id": "resume_denoise", "completed_ids": ["done_1", "done_2"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    config = {
        "workflow": {"id": "resume_denoise", "checkpoint": True, "resume": True},
        "input": {"type": "jsonl", "path": str(input_path)},
        "output": {"run_dir": str(run_dir), "clean_path": "clean.jsonl", "dropped_path": "dropped.jsonl", "review_path": "review.jsonl"},
        "steps": [{"id": "text_denoise", "operator": "text_denoise", "params": {"thresholds": {"keep_score": 0.0, "review_score": 0.0, "hard_fail_issues": []}}}],
    }
    from denoise_workflow_engine.runtime.registry import build_default_registry

    summary = WorkflowExecutor(config, build_default_registry()).run()

    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert summary["total_count"] == 2
    assert summary["current_run_count"] == 0
    assert summary["input_total_count"] == 2
    assert summary["historical_completed_count"] == 2
    assert summary["newly_processed_count"] == 0
    assert summary["current_completed_count"] == 2
    assert summary["pending_count"] == 0
    assert "| total_count | 2 |" in report
    assert "| current_run_count | 0 |" in report
    assert "| completed_count | 2 |" in report
    assert "| historical_completed_count | 2 |" in report
    assert "| newly_processed_count | 0 |" in report


def test_workflow_concurrency_processes_samples_in_parallel(tmp_path: Path) -> None:
    """Verify that the workflow executes operators in parallel at sample level.

    Business logic:
        1. Register a test operator that records concurrency overlap.
        2. Execute three JSONL samples with `concurrency=2`.
        3. Assert that overlap occurs while output order stays aligned with input order.

    Args:
            tmp_path (Path): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> callable(test_workflow_concurrency_processes_samples_in_parallel)
        True
    """

    class SlowDenoiseOperator(BaseOperator):
        operator_name = "slow_denoise_operator"  # Registration name for the concurrency test operator.
        active = 0  # Number of samples currently being processed, used to observe overlap.
        max_active = 0  # Maximum concurrent sample count observed during the test.
        lock = threading.Lock()  # Thread lock protecting `active` and `max_active`.

        def process(self, item: dict[str, Any]) -> dict[str, Any]:
            """Record concurrency overlap and keep the sample.

            Business logic:
                1. Increment the active counter on entry.
                2. Sleep briefly to create a concurrency window.
                3. Decrement the counter on exit and mark the sample as keep.

            Args:
                    item (dict[str, Any]): Current sample dictionary.

            Returns:
                dict[str, Any]: Sample marked as keep.

            Examples:
                >>> hasattr(SlowDenoiseOperator, "operator_name")
                True
            """
            with self.lock:
                type(self).active += 1
                type(self).max_active = max(type(self).max_active, type(self).active)
            time.sleep(0.05)
            with self.lock:
                type(self).active -= 1
            item["action"] = "keep"
            return item

    registry = OperatorRegistry()
    registry.register(SlowDenoiseOperator)
    input_path = tmp_path / "input.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "a", "payload": {"text": "a"}}, ensure_ascii=False),
                json.dumps({"id": "b", "payload": {"text": "b"}}, ensure_ascii=False),
                json.dumps({"id": "c", "payload": {"text": "c"}}, ensure_ascii=False),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    config = {
        "workflow": {"id": "concurrent_denoise", "checkpoint": True, "concurrency": 2},
        "input": {"type": "jsonl", "path": str(input_path)},
        "output": {"run_dir": str(run_dir), "clean_path": "clean.jsonl", "dropped_path": "dropped.jsonl", "review_path": "review.jsonl"},
        "steps": [{"id": "slow", "operator": "slow_denoise_operator", "params": {}}],
    }

    summary = WorkflowExecutor(config, registry).run()

    rows = [json.loads(line) for line in (run_dir / "clean.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert [row["id"] for row in rows] == ["a", "b", "c"]
    assert SlowDenoiseOperator.max_active >= 2
    assert summary["concurrency"] == 2
    assert summary["concurrency_enabled"] is True


def test_modality_router_selects_text() -> Any:
    """test modality router selects text

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_modality_router_selects_text
        test_modality_router_selects_text
    """
    item = {"id": "t1", "payload": {"text": "some text"}}
    out = ModalityRouterOperator({}).process(item)
    assert out["modality"] == "text"
    assert out["meta"]["selected_module"] == "text_denoise"


def test_modality_router_selects_image_text_pair() -> Any:
    """test modality router selects image text pair

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_modality_router_selects_image_text_pair
        test_modality_router_selects_image_text_pair
    """
    item = {"id": "p1", "payload": {"text": "caption", "image_path": "a.jpg"}}
    out = ModalityRouterOperator({}).process(item)
    assert out["modality"] == "image_text_pair"
    assert out["meta"]["selected_module"] == "image_text_pair_denoise"


def test_leakage_guard_flags_expected_fields() -> Any:
    """test leakage guard flags expected fields

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_leakage_guard_flags_expected_fields
        test_leakage_guard_flags_expected_fields
    """
    item = {"id": "x", "payload": {"text": "abc"}, "expected_action": "keep"}
    out = DataLeakageGuardOperator({}).process(item)
    assert "data_leakage_suspected" in out["issues"]
    assert out["metrics"]["data_leakage_guard_passed"] is False


def test_leakage_guard_flags_reference_answers() -> Any:
    """test leakage guard flags reference answers

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_leakage_guard_flags_reference_answers
        test_leakage_guard_flags_reference_answers
    """
    item = {"id": "x", "payload": {"image_path": "a.jpg", "reference_image_path": "clean.jpg"}}
    out = DataLeakageGuardOperator({}).process(item)
    assert "data_leakage_suspected" in out["issues"]
    assert out["metrics"]["data_leakage_guard_passed"] is False


def test_leakage_guard_passes_normal_item() -> Any:
    """test leakage guard passes normal item

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_leakage_guard_passes_normal_item
        test_leakage_guard_passes_normal_item
    """
    item = {"id": "x", "payload": {"text": "abc"}}
    out = DataLeakageGuardOperator({}).process(item)
    assert out["metrics"]["data_leakage_guard_passed"] is True


def test_text_sensitive_detect_masks_valid_id_card() -> None:
    """test text sensitive detect masks valid id card

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_masks_valid_id_card
        test_text_sensitive_detect_masks_valid_id_card
    """
    item = {"id": "x", "payload": {"text": "ID card 440308199901101512 should be masked."}, "modality": "text"}

    out = TextSensitiveDetectOperator({}).process(item)

    assert out["payload"]["text"] == "ID card [ID_CARD] should be masked."
    assert "text_sensitive_masked" in out["issues"]
    assert out["metrics"]["text_sensitive_types"] == ["id_card"]


def test_text_sensitive_detect_keeps_invalid_id_card_checksum() -> None:
    """test text sensitive detect keeps invalid id card checksum

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_keeps_invalid_id_card_checksum
        test_text_sensitive_detect_keeps_invalid_id_card_checksum
    """
    text = "Invalid ID card 440308199901101513 should not be masked."
    item = {"id": "x", "payload": {"text": text}, "modality": "text"}

    out = TextSensitiveDetectOperator({}).process(item)

    assert out["payload"]["text"] == text
    assert "issues" not in out


def test_text_sensitive_detect_validates_professional_candidates() -> None:
    """test text sensitive detect validates professional candidates

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_validates_professional_candidates
        test_text_sensitive_detect_validates_professional_candidates
    """
    item = {
        "id": "x",
        "payload": {
            "text": "Bank card 4111111111111111 phone 13800138000 email user@example.com URL https://192.168.1.1/a IP 192.168.1.2"
        },
        "modality": "text",
    }

    out = TextSensitiveDetectOperator({}).process(item)

    assert "[BANK_CARD]" in out["payload"]["text"]
    assert "[PHONE]" in out["payload"]["text"]
    assert "[EMAIL]" in out["payload"]["text"]
    assert "[URL]" in out["payload"]["text"]
    assert "[IP]" in out["payload"]["text"]
    assert "https://[IP]" not in out["payload"]["text"]
    assert set(out["metrics"]["text_sensitive_types"]) >= {"bank_card", "phone", "email", "url", "ip"}


def test_text_sensitive_detect_masks_valid_mac_address() -> None:
    """test text sensitive detect masks valid mac address

    Business logic:
        1. Build a text sample containing one valid MAC address.
        2. Execute `TextSensitiveDetectOperator`.
        3. Assert that the MAC address is masked and the detected type is recorded.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_masks_valid_mac_address
        test_text_sensitive_detect_masks_valid_mac_address
    """
    item = {"id": "x", "payload": {"text": "Switch MAC 00:1A:2B:3C:4D:5E must be masked."}, "modality": "text"}

    out = TextSensitiveDetectOperator({}).process(item)

    assert out["payload"]["text"] == "Switch MAC [MAC_ADDRESS] must be masked."
    assert "text_sensitive_masked" in out["issues"]
    assert "mac_address" in out["metrics"]["text_sensitive_types"]


def test_text_sensitive_detect_keeps_invalid_professional_candidates() -> None:
    """test text sensitive detect keeps invalid professional candidates

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_keeps_invalid_professional_candidates
        test_text_sensitive_detect_keeps_invalid_professional_candidates
    """
    text = "Card 4111111111111112 phone 12345678901 email bad@@example URL https://bad_domain IP 999.1.1.1"
    item = {"id": "x", "payload": {"text": text}, "modality": "text"}

    out = TextSensitiveDetectOperator({}).process(item)

    assert out["payload"]["text"] == text
    assert "issues" not in out


def test_language_detect_uses_local_model_and_marks_short_unknown() -> None:
    """test language detect uses local model and marks short unknown

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_language_detect_uses_local_model_and_marks_short_unknown
        test_language_detect_uses_local_model_and_marks_short_unknown
    """
    operator = LanguageDetectOperator({"allowed_languages": ["zh", "en", "mixed"]})
    zh = operator.process({"id": "zh", "payload": {"text": "这是一个 language detection regression 用中文样本。"}, "modality": "text"})
    en = operator.process({"id": "en", "payload": {"text": "This is a local language detection test."}, "modality": "text"})
    short = operator.process({"id": "s", "payload": {"text": "OK"}, "modality": "text"})

    assert zh["metrics"]["language"] == "zh"
    assert en["metrics"]["language"] == "en"
    assert short["metrics"]["language"] == "unknown"
    assert short["metrics"]["language_distribution"]["method"] == "lingua"
    assert "language_unknown" in short["issues"]


def test_sensitive_content_records_rule_evidence_after_normalization() -> None:
    """test sensitive content records rule evidence after normalization

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_sensitive_content_records_rule_evidence_after_normalization
        test_sensitive_content_records_rule_evidence_after_normalization
    """
    item = {"id": "x", "payload": {"text": "This content includes 刷-单 返 利 tokens for normalization testing"}, "modality": "text"}

    out = SensitiveContentFilter({}).process(item)

    assert "sensitive_risk" in out["issues"]
    assert out["metrics"]["sensitive_categories"] == {"fraud": ["刷单返利"]}
    assert out["metrics"]["sensitive_detection_method"] == "normalized_keyword_rules"
    assert out["metrics"]["sensitive_detection_confidence"] < 0.5


def test_qrcode_heuristic_does_not_emit_confirmed_issue(tmp_path: Any) -> None:
    """test qrcode heuristic does not emit confirmed issue

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            tmp_path (Any): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_qrcode_heuristic_does_not_emit_confirmed_issue
        test_qrcode_heuristic_does_not_emit_confirmed_issue
    """
    from PIL import Image, ImageDraw

    path = tmp_path / "corner.png"
    image = Image.new("RGB", (256, 256), "white")
    draw = ImageDraw.Draw(image)
    for index in range(0, 90, 8):  # Create corner stripes to verify that the heuristic does not false-positive on QR codes.
        color = "black" if index % 16 == 0 else "white"
        draw.rectangle((index, 0, index + 5, 90), fill=color)
        draw.rectangle((0, index, 90, index + 5), fill=color)
    image.save(path)

    out = QRCodeDetectOperator({}).process({"id": "x", "payload": {"image_path": str(path)}, "modality": "image"})

    assert "qrcode_detected" not in out.get("issues", [])
    assert out["metrics"]["qr_detected"] is False


def test_qrcode_decoder_marks_real_qrcode(tmp_path: Any) -> None:
    """test qrcode decoder marks real qrcode

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            tmp_path (Any): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_qrcode_decoder_marks_real_qrcode
        test_qrcode_decoder_marks_real_qrcode
    """
    import qrcode

    path = tmp_path / "qr.png"
    image = qrcode.make("https://example.com/check")
    image.save(path)

    out = QRCodeDetectOperator({}).process({"id": "x", "payload": {"image_path": str(path)}, "modality": "image"})

    assert "qrcode_detected" in out["issues"]
    assert out["metrics"]["qr_detected"] is True
    assert out["metrics"]["qr_decoded_text"] == "https://example.com/check"
    assert out["metrics"]["qr_detection_confidence"] >= 0.9


def test_reference_quality_uses_scikit_image_metrics(tmp_path: Any) -> None:
    """test reference quality uses scikit image metrics

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            tmp_path (Any): Pytest temporary directory.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_reference_quality_uses_scikit_image_metrics
        test_reference_quality_uses_scikit_image_metrics
    """
    from PIL import Image

    left = tmp_path / "left.png"
    right = tmp_path / "right.png"
    Image.new("RGB", (32, 32), "white").save(left)
    Image.new("RGB", (32, 32), "white").save(right)
    item = {
        "id": "x",
        "payload": {"image_path": str(left), "reference_image_path": str(right)},
        "modality": "image",
    }

    out = ReferenceImageQualityOperator({}).process(item)

    assert out["metrics"]["reference_quality_method"] == "scikit_image_metrics"
    assert out["metrics"]["reference_ssim"] == 1.0
    assert out["metrics"]["reference_psnr"] >= 90


def test_image_text_pair_insufficient_evidence_does_not_default_to_one() -> None:
    """test image text pair insufficient evidence does not default to one

    Business logic:
        1. Build a test sample, temporary file, or operator instance.
        2. Execute the target operator or helper function.
        3. Assert that issues, actions, metrics, or outputs match the regression expectation.

    Args:
            None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_image_text_pair_insufficient_evidence_does_not_default_to_one
        test_image_text_pair_insufficient_evidence_does_not_default_to_one
    """
    item = {"id": "p", "payload": {"text": "caption only"}, "modality": "image_text_pair", "metrics": {}}

    item = ImageTextKeywordSimilarityOperator({}).process(item)
    item = setup_operator(CLIPImageTextSimilarityOperator({})).process(item)
    item = OCRTextConsistencyOperator({}).process(item)
    item = OCRKeyFieldConsistencyOperator({}).process(item)
    item = setup_operator(VLMConsistencyOperator({})).process(item)

    assert item["metrics"]["image_text_similarity_score"] is None
    assert item["metrics"]["clip_similarity_score"] is None
    assert item["metrics"]["ocr_consistency_score"] is None
    assert item["metrics"]["ocr_key_field_consistency_score"] is None
    assert item["metrics"]["vlm_consistency_score"] is None
    assert item["metrics"]["vlm_consistency_source"] == "insufficient_evidence"


def test_image_safety_local_fallback_tolerates_unreadable_image(tmp_path: Any) -> None:
    """Verify that local image safety detection degrades safely on unreadable images.

    Business logic:
        1. Write a temporary file whose extension is png but whose content is undecodable.
        2. Execute the local fallback path of the image safety operator.
        3. Confirm that the error does not bubble into a NameError and does not falsely report safety risk.

    Args:
        tmp_path (Any): Temporary directory provided by pytest.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_image_safety_local_fallback_tolerates_unreadable_image(tmp_path)
        None
    """
    broken_image = tmp_path / "broken.png"
    broken_image.write_bytes(b"not an image")

    item = setup_operator(ImageSafetyOperator({})).process(
        {"id": "broken", "payload": {"image_path": str(broken_image)}, "modality": "image"}
    )

    assert item["metrics"]["safety_mode"] == "local_fallback"
    assert item["metrics"]["safety_safe"] is True
    assert item["metrics"]["safety_confidence"] == 0.0
    assert "safety_risk" not in item.get("issues", [])


def test_video_repair_uses_project_root_when_issue_is_repairable(tmp_path: Any) -> None:
    """Verify that the video-repair path still resolves the project root correctly.

    Business logic:
        1. Build a video sample with a repairable issue so the repair operator enters the ffmpeg branch.
        2. Use a temporary output directory to avoid polluting project outputs.
        3. Confirm that failures record ffmpeg errors rather than crashing early because ROOT is undefined.

    Args:
        tmp_path (Any): Temporary directory provided by pytest.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_video_repair_uses_project_root_when_issue_is_repairable(tmp_path)
        None
    """
    src = tmp_path / "source.mp4"
    src.write_bytes(b"fake video bytes")
    item = {
        "id": "video1",
        "payload": {"video_path": str(src)},
        "modality": "video",
        "issues": ["low_audio_volume"],
    }

    out = VideoRepairOperator({"output_dir": str(tmp_path / "repaired"), "timeout": 1}).process(item)

    assert "video_repair_failed" in out["issues"]
    assert out["metrics"]["video_repair_applied"] is False
    assert out["metrics"]["video_repair_error"]
