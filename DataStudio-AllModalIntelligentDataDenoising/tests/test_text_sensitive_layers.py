from denoise_workflow_engine.operators.text_denoising.assessors import TextPhoneAssessor
from denoise_workflow_engine.operators.text_denoising.governors import TextPhoneGovernor
from denoise_workflow_engine.operators.text_denoising.pipelines import TextSensitiveDetectPipeline


def test_text_phone_assessor_detects_valid_phone() -> None:
    """Verify that the phone assessor only detects and evaluates phone numbers.

    Business logic:
        1. Build text containing a valid phone number.
        2. Execute `TextPhoneAssessor.assess`.
        3. Assert the detected type, candidates, score, and reason.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_phone_assessor_detects_valid_phone()
        None
    """
    result = TextPhoneAssessor().assess("Please contact 13800138000")

    assert result.sensitive_type == "phone"
    assert result.detected is True
    assert result.candidates == ["13800138000"]
    assert result.score == 0.0
    assert "phone" in result.reason.lower()


def test_text_phone_assessor_ignores_invalid_phone() -> None:
    """Verify that the phone assessor ignores invalid phone candidates.

    Business logic:
        1. Build text containing an invalid phone-like number.
        2. Execute `TextPhoneAssessor.assess`.
        3. Assert that nothing is detected and no candidates are returned.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_phone_assessor_ignores_invalid_phone()
        None
    """
    result = TextPhoneAssessor().assess("Code 12345678901 should not be treated as a phone number")

    assert result.detected is False
    assert result.candidates == []
    assert result.score == 1.0


def test_text_phone_governor_only_masks_assessed_candidates() -> None:
    """Verify that the phone governor masks only candidates present in the assessment.

    Business logic:
        1. Use the assessor to identify the first phone number.
        2. Pass text containing an additional phone number to the governor.
        3. Assert that the governor does not detect candidates outside the assessment.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_phone_governor_only_masks_assessed_candidates()
        None
    """
    assessment = TextPhoneAssessor().assess("Please contact 13800138000")
    text = "Please contact 13800138000, backup 13900139000"

    assert TextPhoneGovernor().govern(text, assessment) == "Please contact [PHONE], backup 13900139000"


def test_text_sensitive_detect_pipeline_preserves_url_before_ip_behavior() -> None:
    """Verify that the text-sensitive pipeline preserves URL-before-IP behavior.

    Business logic:
        1. Build text containing both an IP inside a URL and a standalone IP.
        2. Execute `TextSensitiveDetectPipeline.run`.
        3. Assert that the URL is not rewritten as `https://[IP]` while the standalone IP is masked.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_pipeline_preserves_url_before_ip_behavior()
        None
    """
    result = TextSensitiveDetectPipeline().run("URL https://192.168.1.1/a IP 192.168.1.2")

    assert "[URL]" in result.text
    assert "[IP]" in result.text
    assert "https://[IP]" not in result.text
    assert result.hit_types == ["url", "ip"]
