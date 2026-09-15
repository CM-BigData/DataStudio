from pathlib import Path
import json

from quality_eval.cli import main
from quality_eval.operators.text_dataset_eval.special_characters import TextSpecialCharactersEvalOperator


def _load_real_text_samples() -> list[dict[str, object]]:
    """Load the reproducible real-text special-character sample subset.

    Business logic:
        1. Resolve the stored sample JSONL fixture path.
        2. Read non-empty lines from the file.
        3. Deserialize every line into a sample dictionary.

    Args:
        None: This helper does not take input parameters.

    Returns:
        list[dict[str, object]]: Real-text special-character sample list.

    Examples:
        >>> isinstance(_load_real_text_samples(), list)
        True
    """
    sample_path = Path("example_data/text_special_characters_sample/samples.jsonl")
    return [json.loads(line) for line in sample_path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_text_special_characters_detects_zero_width_char() -> None:
    """Verify that zero-width characters are detected.

    Business logic:
        1. Build text containing one zero-width space.
        2. Execute the special-characters operator.
        3. Assert that the invisible-character metric and issue are written back.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_special_characters_detects_zero_width_char()
        None
    """
    sample = {"payload": {"text": "请复制这段文\u200b本后再提交。"}, "metrics": {}, "issues": []}

    result = TextSpecialCharactersEvalOperator({}).process(sample)

    assert result["metrics"]["special_characters_ok"] is False
    assert result["metrics"]["invisible_character_count"] == 1
    assert "special_characters_abnormal" in result["issues"]


def test_text_special_characters_detects_control_char() -> None:
    """Verify that disallowed control characters are detected.

    Business logic:
        1. Build text containing a bell control character.
        2. Execute the operator.
        3. Assert that the control-character metric and issue are written back.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_special_characters_detects_control_char()
        None
    """
    sample = {"payload": {"text": "客服回复如下：\u0007请重新登录后再试。"}, "metrics": {}, "issues": []}

    result = TextSpecialCharactersEvalOperator({}).process(sample)

    assert result["metrics"]["special_characters_ok"] is False
    assert result["metrics"]["control_character_count"] == 1
    assert "special_characters_abnormal" in result["issues"]


def test_text_special_characters_detects_mojibake_residue() -> None:
    """Verify that mojibake residues are detected.

    Business logic:
        1. Build text containing a common mojibake fragment.
        2. Execute the operator.
        3. Assert that the mojibake-fragment metric and issue are written back.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_special_characters_detects_mojibake_residue()
        None
    """
    sample = {"payload": {"text": "ï»¿最新公告：平台将于今晚进行例行维护。"}, "metrics": {}, "issues": []}

    result = TextSpecialCharactersEvalOperator({}).process(sample)

    assert result["metrics"]["special_characters_ok"] is False
    assert result["metrics"]["mojibake_fragment_count"] >= 1
    assert "special_characters_abnormal" in result["issues"]


def test_text_special_characters_accepts_normal_multiline_text() -> None:
    """Verify that normal newline and tab characters remain allowed.

    Business logic:
        1. Build normal instructional text with a newline and a tab.
        2. Execute the operator.
        3. Assert that the allowlisted controls do not trigger an issue.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_special_characters_accepts_normal_multiline_text()
        None
    """
    sample = {"payload": {"text": "第一步：下载文件。\n第二步：解压并运行安装程序。\t完成后重启。"}, "metrics": {}, "issues": []}

    result = TextSpecialCharactersEvalOperator({}).process(sample)

    assert result["metrics"]["special_characters_ok"] is True
    assert result["metrics"]["special_character_count"] == 0
    assert result["issues"] == []


def test_text_special_characters_workflow_with_real_samples() -> None:
    """Verify that the real-text special-character workflow runs and separates hits from passes.

    Business logic:
        1. Run the dedicated special-character workflow on the stored real-text subset.
        2. Read the result JSONL file and index rows by sample id.
        3. Assert that dirty and clean real-text samples produce the expected issue outcomes.

    Args:
        None: This test does not take input parameters.

    Returns:
        None: Expectations are expressed through pytest assertions.

    Examples:
        >>> test_text_special_characters_workflow_with_real_samples()
        None
    """
    output_dir = "test_runs/pytest_text_special_characters_real"
    assert main(["run", "-c", "workflows/text_special_characters_eval.yaml", "--task-id", "pytest_text_special_characters_real", "--output-dir", output_dir]) == 0
    rows = [
        json.loads(line)
        for line in (Path(output_dir) / "text_special_characters_eval_result.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {row["sample_id"]: row for row in rows}

    assert "special_characters_abnormal" in by_id["webpage_crawl_bom"]["issues"]
    assert by_id["webpage_crawl_clean"]["issues"] == []
    assert "special_characters_abnormal" in by_id["copy_paste_zero_width"]["issues"]
    assert "special_characters_abnormal" in by_id["copy_paste_soft_hyphen"]["issues"]
    assert "special_characters_abnormal" in by_id["hidden_char_control"]["issues"]
    assert by_id["normal_multiline_text"]["issues"] == []
    assert "special_characters_abnormal" in by_id["encoding_residue_quote"]["issues"]
    assert "special_characters_abnormal" in by_id["hidden_char_word_joiner"]["issues"]


def test_real_text_samples_are_reproducible() -> None:
    """Verify that the stored real-text sample subset remains loadable and non-empty.

    Business logic:
        1. Load the stored real-text special-character samples.
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
