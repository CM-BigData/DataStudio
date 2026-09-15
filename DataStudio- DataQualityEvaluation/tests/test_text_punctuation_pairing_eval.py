from pathlib import Path
import json

from quality_eval.cli import main
from quality_eval.operators.text_dataset_eval.quality import TextPunctuationPairingEvalOperator


def _load_real_text_samples() -> list[dict[str, object]]:
    """Load the reproducible real-text punctuation sample subset.

    Business logic:
        1. Resolve the stored sample JSONL fixture path.
        2. Read non-empty lines from the file.
        3. Deserialize every line into a sample dictionary.

    Args:
        None: This helper does not take input parameters.

    Returns:
        list[dict[str, object]]: Real-text punctuation sample list.

    Examples:
        >>> isinstance(_load_real_text_samples(), list)
        True
    """
    sample_path = Path("example_data/text_punctuation_pairing_sample/samples.jsonl")

    return [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_text_punctuation_pairing_accepts_balanced_text() -> None:
    """Verify that balanced paired punctuation passes the operator.

    Business logic:
        1. Build text with correctly nested Chinese book-title marks, quotes, and parentheses.
        2. Execute the punctuation-pairing operator.
        3. Assert that the sample remains issue-free and writes successful metrics.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_punctuation_pairing_accepts_balanced_text()
        None
    """
    sample = {"payload": {"text": "文章《人工智能导论（第三版）》对“模型评估”章节做了修订。"}, "metrics": {}, "issues": []}

    result = TextPunctuationPairingEvalOperator({}).process(sample)

    assert result["metrics"]["punctuation_pairing_ok"] is True
    assert result["metrics"]["unpaired_punctuation_count"] == 0
    assert result["metrics"]["mismatched_punctuation_count"] == 0
    assert result["issues"] == []


def test_text_punctuation_pairing_detects_missing_right_parenthesis() -> None:
    """Verify that a missing right parenthesis is detected.

    Business logic:
        1. Build text with one missing Chinese right parenthesis.
        2. Execute the punctuation-pairing operator.
        3. Assert that the operator records an unpaired punctuation issue.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_punctuation_pairing_detects_missing_right_parenthesis()
        None
    """
    sample = {"payload": {"text": "论坛求助：我把配置写成了（默认开启，结果服务起不来。"}, "metrics": {}, "issues": []}

    result = TextPunctuationPairingEvalOperator({}).process(sample)

    assert result["metrics"]["punctuation_pairing_ok"] is False
    assert result["metrics"]["unpaired_punctuation_count"] == 1
    assert "punctuation_pairing_abnormal" in result["issues"]


def test_text_punctuation_pairing_detects_quote_mismatch() -> None:
    """Verify that quote mismatches are detected.

    Business logic:
        1. Build text where a Chinese opening double quote closes with a straight single quote.
        2. Execute the punctuation-pairing operator.
        3. Assert that the operator records both mismatch metrics and the issue code.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_punctuation_pairing_detects_quote_mismatch()
        None
    """
    sample = {"payload": {"text": "文档要求写明“适用范围'，否则审核无法通过。"}, "metrics": {}, "issues": []}

    result = TextPunctuationPairingEvalOperator({}).process(sample)

    assert result["metrics"]["punctuation_pairing_ok"] is False
    assert result["metrics"]["unpaired_punctuation_count"] >= 1
    assert "punctuation_pairing_abnormal" in result["issues"]


def test_text_punctuation_pairing_handles_mixed_chinese_english_scene() -> None:
    """Verify that balanced mixed Chinese-English punctuation is not misclassified.

    Business logic:
        1. Build mixed-language text with balanced straight quotes, Chinese quotes, and full-width parentheses.
        2. Execute the punctuation-pairing operator.
        3. Assert that the operator preserves a passing result.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_punctuation_pairing_handles_mixed_chinese_english_scene()
        None
    """
    sample = {"payload": {"text": "Release note: update the field name from \"title\" to “display_title”（兼容旧版本）。"}, "metrics": {}, "issues": []}

    result = TextPunctuationPairingEvalOperator({}).process(sample)

    assert result["metrics"]["punctuation_pairing_ok"] is True
    assert result["issues"] == []


def test_text_punctuation_pairing_workflow_with_real_samples() -> None:
    """Verify that the real-text punctuation workflow runs and separates hits from passes.

    Business logic:
        1. Run the dedicated punctuation-pairing workflow on the stored real-text subset.
        2. Read the result JSONL file and index rows by sample id.
        3. Assert that balanced and unbalanced real-text samples produce the expected issue outcomes.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_punctuation_pairing_workflow_with_real_samples()
        None
    """
    output_dir = "test_runs/pytest_text_punctuation_pairing_real"
    assert main(["run", "-c", "workflows/text_punctuation_pairing_eval.yaml", "--task-id", "pytest_text_punctuation_pairing_real", "--output-dir", output_dir]) == 0
    rows = [
        json.loads(line)
        for line in (Path(output_dir) / "text_punctuation_pairing_eval_result.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {row["sample_id"]: row for row in rows}

    assert by_id["news_balanced_quotes"]["issues"] == []
    assert "punctuation_pairing_abnormal" in by_id["forum_missing_right_parenthesis"]["issues"]
    assert "punctuation_pairing_abnormal" in by_id["document_mismatched_quote"]["issues"]
    assert by_id["mixed_language_balanced"]["issues"] == []
    assert "punctuation_pairing_abnormal" in by_id["forum_unclosed_bracket"]["issues"]


def test_real_text_samples_are_reproducible() -> None:
    """Verify that the stored real-text sample subset remains loadable and non-empty.

    Business logic:
        1. Load the stored real-text punctuation samples.
        2. Assert that the subset size is within the intended small validation range.
        3. Assert that every sample has non-empty text content.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_real_text_samples_are_reproducible()
        None
    """
    samples = _load_real_text_samples()
    assert 5 <= len(samples) <= 10
    assert all(str(sample["text"]).strip() for sample in samples)
