from __future__ import annotations

from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator
from synthesis_engine.utilities.scoring import _signature



class SafetyFilterOperator(BaseOperator):
    operator_name = "safety_filter"  # Registry name for the safety-word filtering workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Mark safety issues using the configured word list

        Business logic:
            1. Read and normalize banned words
            2. Extract the sample signature text
            3. Append a safety issue when a banned word is matched

        Args:
            item (GenerationItem): Sample to filter.

        Returns:
            GenerationItem: Sample carrying safety issues.

        Examples:
            >>> SafetyFilterOperator().operator_name
            'safety_filter'
        """
        banned_words = [word.lower() for word in self.config.get("banned_words", [])]
        text = _signature(item).lower()
        for word in banned_words:  # Check each configured safety word with substring matching.
            if word and word in text:  # Skip empty entries and record an issue on non-empty matches.
                item.issues.append({"type": "unsafe_content", "message": f"Matched banned term: {word}"})
        return item


class QualityGateOperator(BaseOperator):
    operator_name = "quality_gate"  # Registry name for the quality-gate workflow entry.

    def process(self, item: GenerationItem) -> GenerationItem:
        """Compute the quality score and decide the sample action

        Business logic:
            1. Compute quality from completeness, diversity, and issue penalties
            2. Accept the sample when it passes and has no issues
            3. Otherwise choose retry or filtering based on the retry limit

        Args:
            item (GenerationItem): Sample to evaluate.

        Returns:
            GenerationItem: Sample updated with quality score and action.

        Examples:
            >>> QualityGateOperator().operator_name
            'quality_gate'
        """
        issue_penalty = float(self.config.get("issue_penalty", 0.2)) * len(item.issues)
        diversity_score = float(item.metrics.get("diversity_score", 1.0))
        completeness_score = 1.0 if item.generated else 0.0
        quality_score = max(0.0, min(1.0, 0.6 * completeness_score + 0.4 * diversity_score - issue_penalty))
        item.metrics["quality_score"] = round(quality_score, 4)

        pass_score = float(self.config.get("pass_score", 0.7))
        if quality_score >= pass_score and not item.issues:  # Accept samples that pass the threshold and have no issues.
            item.action = "accepted"
        elif int(item.lineage.get("retry_attempt", 0)) < int(self.config.get("retry_limit", 0)):
            item.action = "needs_retry"
        else:
            item.action = "filtered"
        return item
