import regex as re

from email_validator import EmailNotValidError, validate_email

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextEmailAssessor(BaseTextAssessor):
    sensitive_type = "email"  # Sensitive information type: email address.
    pattern = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w.+-])")  # Candidate regex that matches email-like strings.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid email addresses.

        Business logic:
            1. Extract email-like fragments with the email regex.
            2. Validate each fragment with `email-validator`.
            3. Return the email assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: Email assessment result.

        Examples:
            >>> TextEmailAssessor().assess("a@example.com").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid email addresses", "No email address detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether an email candidate is well-formed.

        Business logic:
            1. Accept an email candidate string.
            2. Validate its format with `email-validator`.
            3. Return whether the candidate is valid.

        Args:
            candidate (str): Email candidate to validate.

        Returns:
            bool: Whether the email is valid.

        Examples:
            >>> TextEmailAssessor().is_valid("a@example.com")
            True
        """
        try:
            validate_email(candidate, check_deliverability=False)
            return True
        except EmailNotValidError:
            return False
