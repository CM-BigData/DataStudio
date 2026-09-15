from quality_eval.utilities.image.shared import *  # noqa: F403

class ImageDatasetScoreOperator(BaseOperator):
    operator_name: str = "image_dataset_score"  # Registered operator name used to aggregate image issues and score samples.

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Calculate a sample score and handling suggestion from image issues.

        Business logic:
            1. Read the issue-penalty table from rules and fall back to the default table when absent.
            2. Sum penalties for all sample issues and clamp the score between 0 and 100.
            3. Map the score to a quality level and handling action.
            4. Generate remediation suggestions from the issue codes.

        Args:
            item (dict[str, Any]): Image sample that already finished quality checks.

        Returns:
            dict[str, Any]: Sample with `score`, `level`, `action`, and `suggestions` written back.

        Examples:
            >>> sample = {"issues": ["image_not_found"]}
            >>> ImageDatasetScoreOperator({}).process(sample)["action"]
            'drop'
        """
        penalties = self.rules.get("issue_penalties", ISSUE_PENALTIES)
        score = 100 - sum(float(penalties.get(issue, ISSUE_PENALTIES.get(issue, 10))) for issue in item["issues"])
        score = max(0, min(100, round(score, 2)))
        item["score"] = score
        item["level"] = level_from_score(score)
        item["action"] = action_from_issues(score, item["issues"])
        item["suggestions"] = suggestions_for(item["issues"])
        return item
