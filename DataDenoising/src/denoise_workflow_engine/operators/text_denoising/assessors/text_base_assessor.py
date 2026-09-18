from __future__ import annotations

from dataclasses import dataclass
import regex as re


@dataclass(frozen=True)
class TextAssessment:
    sensitive_type: str  # Sensitive information category identified by this assessment.
    detected: bool  # Whether any valid candidate was detected.
    candidates: list[str]  # Validated raw candidate fragments collected from the text.
    score: float  # Assessment score: 1 means pass, 0 means sensitive-info risk exists.
    reason: str  # Human-readable reason describing the hit or miss result.


class BaseTextAssessor:
    sensitive_type: str = ""  # Sensitive information type declared by the concrete assessor.
    pattern: re.Pattern[str] | None = None  # Candidate regex used to extract fragments for validation.

    def assess(self, text: str) -> TextAssessment:
        """Assess sensitive-information candidates found in text.

        Business logic:
            1. Extract candidate fragments from the text.
            2. Validate whether each candidate is truly meaningful.
            3. Return the assessment result, score, and reason.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: Sensitive-information assessment result.

        Examples:
            >>> BaseTextAssessor().assess("abc")
            Traceback (most recent call last):
            ...
            NotImplementedError
        """
        raise NotImplementedError

    def _extract_valid_candidates(self, text: str) -> list[str]:
        """Extract and validate candidate fragments from text.

        Business logic:
            1. Use the current assessor regex to extract raw candidates.
            2. Trim trailing punctuation while preserving the original candidate shape.
            3. Return only candidates that pass concrete validation.

        Args:
            text (str): Text to assess.

        Returns:
            list[str]: List of valid candidates.

        Examples:
            >>> BaseTextAssessor()._extract_valid_candidates("abc")
            []
        """
        if self.pattern is None:  # No candidate extraction is possible without a declared regex.
            return []
        candidates = []
        for match in self.pattern.finditer(text):  # Validate regex matches one by one.
            candidate = self.clean_candidate(match.group(0))
            if self.is_valid(candidate):  # Only professionally validated candidates enter the final result.
                candidates.append(candidate)
        return candidates

    def _build_result(self, candidates: list[str], hit_reason: str, miss_reason: str = "") -> TextAssessment:
        """Build a normalized assessment result object.

        Business logic:
            1. Decide whether the assessment is a hit from the candidate list.
            2. Return a failing score and hit reason when candidates exist.
            3. Return a passing score and miss reason otherwise.

        Args:
            candidates (list[str]): Valid candidate list.
            hit_reason (str): Reason used when a hit is detected.
            miss_reason (str, optional): Reason used when no hit is detected.

        Returns:
            TextAssessment: Sensitive-information assessment result.

        Examples:
            >>> BaseTextAssessor()._build_result([], "hit").detected
            False
        """
        detected = bool(candidates)
        return TextAssessment(
            sensitive_type=self.sensitive_type,
            detected=detected,
            candidates=candidates,
            score=0.0 if detected else 1.0,
            reason=hit_reason if detected else miss_reason,
        )

    def clean_candidate(self, candidate: str) -> str:
        """Normalize a raw candidate fragment before validation.

        Business logic:
            1. Accept a regex-matched candidate fragment.
            2. Remove common trailing punctuation.
            3. Return a candidate suitable for validation and governance.

        Args:
            candidate (str): Regex-matched candidate text.

        Returns:
            str: Cleaned candidate text.

        Examples:
            >>> BaseTextAssessor().clean_candidate("a。")
            'a'
        """
        return candidate.rstrip(".,;，。；")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a cleaned candidate is truly meaningful.

        Business logic:
            1. Accept a cleaned candidate string.
            2. Let the concrete assessor apply domain-specific validation.
            3. Return whether the candidate is valid.

        Args:
            candidate (str): Candidate text to validate.

        Returns:
            bool: Whether the candidate is valid.

        Examples:
            >>> BaseTextAssessor().is_valid("abc")
            False
        """
        return False
