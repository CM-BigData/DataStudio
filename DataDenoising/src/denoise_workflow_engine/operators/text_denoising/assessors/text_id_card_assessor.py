import regex as re

from id_validator import validator as id_card_validator

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextIdCardAssessor(BaseTextAssessor):
    sensitive_type = "id_card"  # Sensitive information type: identity card number.
    pattern = re.compile(r"(?<!\d)(?:\d{15}|\d{17}[\dXx])(?!\d)")  # Candidate regex that matches 15-digit and 18-digit ID-card shapes.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid ID card numbers.

        Business logic:
            1. Extract ID-card-like fragments with the candidate regex.
            2. Validate each fragment with `id-validator`.
            3. Return the ID card assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: ID card assessment result.

        Examples:
            >>> TextIdCardAssessor().assess("440308199901101512").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid ID card numbers", "No ID card number detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether an ID card candidate is real.

        Business logic:
            1. Accept an ID card candidate string.
            2. Validate area, date, and checksum with `id-validator`.
            3. Return whether the candidate is valid.

        Args:
            candidate (str): ID card candidate to validate.

        Returns:
            bool: Whether the ID card number is valid.

        Examples:
            >>> TextIdCardAssessor().is_valid("440308199901101512")
            True
        """
        return id_card_validator.is_valid(candidate)
