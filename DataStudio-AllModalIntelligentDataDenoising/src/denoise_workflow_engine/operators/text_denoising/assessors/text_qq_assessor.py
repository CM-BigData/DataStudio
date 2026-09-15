import regex as re

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextQQAssessor(BaseTextAssessor):
    sensitive_type = "qq"  # Sensitive information type: QQ account number.
    pattern = re.compile(r"(?:QQ|qq|qq_id)\s*[:：]?\s*[1-9]\d{4,11}")  # Candidate regex that matches QQ numbers with context keywords.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains QQ account identifiers.

        Business logic:
            1. Extract QQ-like fragments with the candidate regex.
            2. Confirm candidates through the contextual keyword pattern.
            3. Return the QQ assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: QQ assessment result.

        Examples:
            >>> TextQQAssessor().assess("QQ:12345").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains QQ account identifiers", "No QQ account detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a QQ candidate is acceptable.

        Business logic:
            1. Accept a QQ candidate that already includes contextual keywords.
            2. Rely on the regex to constrain digit count and first digit.
            3. Return that the candidate is valid.

        Args:
            candidate (str): QQ candidate text.

        Returns:
            bool: Whether the QQ candidate is valid.

        Examples:
            >>> TextQQAssessor().is_valid("QQ:12345")
            True
        """
        return True
