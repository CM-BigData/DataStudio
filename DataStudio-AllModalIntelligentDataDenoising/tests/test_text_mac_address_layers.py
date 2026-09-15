from pathlib import Path
import json

from denoise_workflow_engine.operators.text_denoising.assessors import TextMacAddressAssessor
from denoise_workflow_engine.operators.text_denoising.governors import TextMacAddressGovernor
from denoise_workflow_engine.operators.text_denoising.pipelines import TextSensitiveDetectPipeline


def _load_real_mac_samples() -> list[dict[str, object]]:
    """Load reproducible real-text MAC samples for regression verification.

    Business logic:
        1. Resolve the fixture file path under `tests/fixtures`.
        2. Read the serialized JSON sample list.
        3. Return the sample payload for tests and smoke validation.

    Args:
        None: This helper does not take input parameters.

    Returns:
        list[dict[str, object]]: Real-text MAC sample definitions.

    Examples:
        >>> isinstance(_load_real_mac_samples(), list)
        True
    """
    fixture_path = Path(__file__).resolve().parent / "fixtures" / "text_mac_address_real_samples" / "samples.json"

    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_text_mac_address_assessor_detects_valid_mac() -> None:
    """Verify that the MAC assessor detects a valid MAC address.

    Business logic:
        1. Build text containing one canonical colon-separated MAC address.
        2. Execute `TextMacAddressAssessor.assess`.
        3. Assert the detected type, candidates, score, and reason.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_mac_address_assessor_detects_valid_mac()
        None
    """
    result = TextMacAddressAssessor().assess("Router MAC 00:1A:2B:3C:4D:5E should be masked")

    assert result.sensitive_type == "mac_address"
    assert result.detected is True
    assert result.candidates == ["00:1A:2B:3C:4D:5E"]
    assert result.score == 0.0
    assert "mac" in result.reason.lower()


def test_text_mac_address_assessor_ignores_hex_noise() -> None:
    """Verify that the MAC assessor ignores hexadecimal noise.

    Business logic:
        1. Build text containing continuous hexadecimal characters without separators.
        2. Execute `TextMacAddressAssessor.assess`.
        3. Assert that the assessor does not report a MAC-address hit.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_mac_address_assessor_ignores_hex_noise()
        None
    """
    result = TextMacAddressAssessor().assess("Checksum 001A2B3C4D5E should stay untouched")

    assert result.detected is False
    assert result.candidates == []
    assert result.score == 1.0


def test_text_mac_address_governor_masks_only_assessed_candidates() -> None:
    """Verify that the MAC governor masks only assessed candidates.

    Business logic:
        1. Use the assessor to identify the first MAC address.
        2. Pass text containing an additional lookalike string to the governor.
        3. Assert that only the assessed MAC candidate is masked.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_mac_address_governor_masks_only_assessed_candidates()
        None
    """
    assessment = TextMacAddressAssessor().assess("Primary MAC 00-1A-2B-3C-4D-5E")
    text = "Primary MAC 00-1A-2B-3C-4D-5E, malformed 00:1A-2B:3C-4D:5E"

    assert TextMacAddressGovernor().govern(text, assessment) == "Primary MAC [MAC_ADDRESS], malformed 00:1A-2B:3C-4D:5E"


def test_text_sensitive_detect_pipeline_masks_mac_address() -> None:
    """Verify that the text-sensitive pipeline masks MAC addresses.

    Business logic:
        1. Build text containing one valid MAC address.
        2. Execute `TextSensitiveDetectPipeline.run`.
        3. Assert that the output text and hit types include the MAC-address layer.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_sensitive_detect_pipeline_masks_mac_address()
        None
    """
    result = TextSensitiveDetectPipeline().run("Asset tag MAC 00:1A:2B:3C:4D:5E must be redacted")

    assert "[MAC_ADDRESS]" in result.text
    assert "mac_address" in result.hit_types


def test_real_mac_text_samples_cover_hits_and_misses() -> None:
    """Verify the real-text MAC sample subset against the assessor.

    Business logic:
        1. Load the real-text fixture subset with expected detection labels.
        2. Execute the MAC assessor on every sample.
        3. Assert that each sample matches the expected hit or miss result.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_real_mac_text_samples_cover_hits_and_misses()
        None
    """
    assessor = TextMacAddressAssessor()
    for sample in _load_real_mac_samples():  # Verify each fixed real-text sample against its expected detection label.
        result = assessor.assess(str(sample["text"]))
        assert result.detected is bool(sample["expected_detected"]), sample["id"]
