from pathlib import Path
import json

from quality_eval.cli import main
from quality_eval.operators.text_dataset_eval.consecutive_punctuation import TextConsecutivePunctuationEvalOperator


def _load_real_text_samples() -> list[dict[str, object]]:
    """Load the reproducible real-text consecutive-punctuation sample subset.

    Business logic:
        1. Resolve the stored sample JSONL fixture path.
        2. Read non-empty lines from the file.
        3. Deserialize every line into a sample dictionary.

    Args:
        None: This helper does not take input parameters.

    Returns:
        list[dict[str, object]]: Real-text consecutive-punctuation sample list.

    Examples:
        >>> isinstance(_load_real_text_samples(), list)
        True
    """
    sample_path = Path("example_data/text_consecutive_punctuation_sample/samples.jsonl")
    return [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_text_consecutive_punctuation_accepts_chinese_ellipsis() -> None:
    """Verify that a common Chinese ellipsis remains allowed.

    Business logic:
        1. Build Chinese text with one ellipsis run.
        2. Execute the consecutive-punctuation operator.
        3. Assert that the sample remains issue-free and metrics stay healthy.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_consecutive_punctuation_accepts_chinese_ellipsis()
        None
    """
    sample = {"payload": {"text": "今天终于下班了……明天继续冲。"}, "metrics": {}, "issues": []}

    result = TextConsecutivePunctuationEvalOperator({}).process(sample)

    assert result["metrics"]["consecutive_punctuation_ok"] is True
    assert result["metrics"]["consecutive_punctuation_count"] == 1
    assert result["metrics"]["consecutive_punctuation_abnormal_count"] == 0
    assert result["issues"] == []


def test_text_consecutive_punctuation_detects_english_repeated_periods() -> None:
    """Verify that repeated ASCII periods above the workflow threshold are detected.

    Business logic:
        1. Build English text with three consecutive periods.
        2. Execute the operator with the workflow-like period threshold.
        3. Assert that the operator reports the abnormal issue.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_consecutive_punctuation_detects_english_repeated_periods()
        None
    """
    sample = {"payload": {"text": "Breaking... update pending"}, "metrics": {}, "issues": []}

    result = TextConsecutivePunctuationEvalOperator({"rules": {"max_period_repeat": 2}}).process(sample)

    assert result["metrics"]["consecutive_punctuation_ok"] is False
    assert result["metrics"]["consecutive_punctuation_abnormal_count"] == 1
    assert "consecutive_punctuation_abnormal" in result["issues"]


def test_text_consecutive_punctuation_accepts_allowed_question_combo() -> None:
    """Verify that a configured question-exclamation combo remains allowed.

    Business logic:
        1. Build mixed-language text with a short allowed punctuation combo.
        2. Execute the operator with the default allowlist.
        3. Assert that the operator does not emit an abnormal issue.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_consecutive_punctuation_accepts_allowed_question_combo()
        None
    """
    sample = {"payload": {"text": "您好！? 这边马上为您核实订单状态。"}, "metrics": {}, "issues": []}

    result = TextConsecutivePunctuationEvalOperator({}).process(sample)

    assert result["metrics"]["consecutive_punctuation_ok"] is True
    assert result["issues"] == []


def test_text_consecutive_punctuation_detects_abnormal_mixed_combo() -> None:
    """Verify that an abnormal mixed punctuation run is detected.

    Business logic:
        1. Build text with an unallowlisted mixed punctuation run.
        2. Execute the consecutive-punctuation operator.
        3. Assert that the abnormal issue and count are written back.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_consecutive_punctuation_detects_abnormal_mixed_combo()
        None
    """
    sample = {"payload": {"text": "这也太离谱了?!!赶紧处理一下。"}, "metrics": {}, "issues": []}

    result = TextConsecutivePunctuationEvalOperator({}).process(sample)

    assert result["metrics"]["consecutive_punctuation_ok"] is False
    assert result["metrics"]["consecutive_punctuation_abnormal_count"] == 1
    assert "consecutive_punctuation_abnormal" in result["issues"]


def test_text_consecutive_punctuation_detects_repeated_question_marks() -> None:
    """Verify that repeated question marks above the threshold are detected.

    Business logic:
        1. Build Chinese question text with four repeated full-width question marks.
        2. Execute the operator with the default repeat threshold.
        3. Assert that the repeated punctuation is flagged.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_consecutive_punctuation_detects_repeated_question_marks()
        None
    """
    sample = {"payload": {"text": "这个接口到底什么时候恢复？？？？"}, "metrics": {}, "issues": []}

    result = TextConsecutivePunctuationEvalOperator({}).process(sample)

    assert result["metrics"]["consecutive_punctuation_ok"] is False
    assert result["metrics"]["consecutive_punctuation_max_run"] == 4
    assert "consecutive_punctuation_abnormal" in result["issues"]


def test_text_consecutive_punctuation_workflow_with_real_samples() -> None:
    """Verify that the real-text consecutive-punctuation workflow runs and separates hits from passes.

    Business logic:
        1. Run the dedicated consecutive-punctuation workflow on the stored real-text subset.
        2. Read the result JSONL file and index rows by sample id.
        3. Assert that allowed and abnormal real-text samples produce the expected issue outcomes.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_consecutive_punctuation_workflow_with_real_samples()
        None
    """
    output_dir = "test_runs/pytest_text_consecutive_punctuation_real"
    assert main(["run", "-c", "workflows/text_consecutive_punctuation_eval.yaml", "--task-id", "pytest_text_consecutive_punctuation_real", "--output-dir", output_dir]) == 0
    rows = [
        json.loads(line)
        for line in (Path(output_dir) / "text_consecutive_punctuation_eval_result.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {row["sample_id"]: row for row in rows}

    assert by_id["social_post_allowed_ellipsis"]["issues"] == []
    assert "consecutive_punctuation_abnormal" in by_id["social_post_abnormal_mixed"]["issues"]
    assert by_id["qa_allowed_question_marks"]["issues"] == []
    assert "consecutive_punctuation_abnormal" in by_id["qa_abnormal_question_marks"]["issues"]
    assert by_id["news_title_clean"]["issues"] == []
    assert "consecutive_punctuation_abnormal" in by_id["news_title_abnormal_periods"]["issues"]
    assert by_id["customer_service_allowed_combo"]["issues"] == []
    assert "consecutive_punctuation_abnormal" in by_id["customer_service_abnormal_commas"]["issues"]


def test_real_text_samples_are_reproducible() -> None:
    """Verify that the stored real-text sample subset remains loadable and non-empty.

    Business logic:
        1. Load the stored real-text consecutive-punctuation samples.
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
