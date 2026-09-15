from quality_eval.utilities.metrics import action_from_issues, level_from_score


def test_level_and_action_rules() -> None:
    """Verify score-level and action-decision rules.

    Business logic:
        1. Check boundary mappings from quality scores to English levels.
        2. Check that high-scoring samples without issues stay as keep.
        3. Check that samples with issues or low scores become review or drop.

    Args:
        None.

    Returns:
        None: The test returns no business value when assertions pass.

    Examples:
        >>> callable(test_level_and_action_rules)
        True
    """
    assert level_from_score(95) == "Excellent"
    assert level_from_score(80) == "Good"
    assert level_from_score(65) == "Average"
    assert level_from_score(20) == "Poor"
    assert action_from_issues(100, []) == "keep"
    assert action_from_issues(70, ["too_short"]) == "review"
    assert action_from_issues(40, ["empty_text"]) == "drop"
