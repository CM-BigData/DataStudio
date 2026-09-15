from .schema import *  # noqa: F403

def level_from_score(score: float) -> str:
    """Map a quality score to an English quality level.

    Business logic:
        1. Scores of 90 or above are marked as the excellent level.
        2. Scores from 75 to 89.99 are marked as the good level.
        3. Scores from 60 to 74.99 are marked as the average level.
        4. Scores below 60 are marked as the poor level.

    Args:
        score (float): Sample quality score.

    Returns:
        str: English quality level.

    Examples:
        >>> isinstance(level_from_score(80), str)
        True
    """
    if score >= 90:  # High-scoring samples can be classified as excellent directly.
        return "Excellent"
    if score >= 75:  # Mid-to-high scores are stable but do not reach the excellent threshold.
        return "Good"
    if score >= 60:  # Passing samples are retained but still require attention.
        return "Average"
    return "Poor"

def action_from_issues(score: float, issues: list[str]) -> str:
    """Determine the handling action from the issue list and score.

    Business logic:
        1. Return `drop` when a mandatory-drop issue is present or the score is below 50.
        2. Return `review` when any issue exists or the score is below 75.
        3. Return `keep` when no issue exists and the score is high enough.

    Args:
        score (float): Sample quality score.
        issues (list[str]): List of sample issue codes.

    Returns:
        str: Handling action, one of `drop`, `review`, or `keep`.

    Examples:
        >>> action_from_issues(100, [])
        'keep'
    """
    if DROP_ISSUES.intersection(issues) or score < 50:  # Unusable issues or very low scores should be dropped directly.
        return "drop"
    if issues or score < 75:  # Samples with fixable issues or lower scores should go to review.
        return "review"
    return "keep"

def suggestions_for(issues: list[str]) -> list[str]:
    """Generate remediation suggestions for issue codes.

    Business logic:
        1. Iterate through the sample issue codes.
        2. Keep only issues that have registered suggestions.
        3. Return the remediation suggestions in the original issue order.

    Args:
        issues (list[str]): List of sample issue codes.

    Returns:
        list[str]: List of remediation suggestions for recognized issues.

    Examples:
        >>> suggestions_for(["empty_text"])[0]
        'Text is empty. Remove it or add content.'
    """
    return [ISSUE_SUGGESTIONS[issue] for issue in issues if issue in ISSUE_SUGGESTIONS]
