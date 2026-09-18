import regex as re

from id_validator import validator as id_card_validator
from stdnum import luhn

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextBankCardAssessor(BaseTextAssessor):
    sensitive_type = "bank_card"  # Sensitive information type: bank card number.
    pattern = re.compile(r"(?<!\d)(?:\d[ -]?){16,19}(?!\d)")  # Candidate regex that matches common bank card lengths.
    id_card_pattern = re.compile(r"(?<!\d)(?:\d{15}|\d{17}[\dXx])(?!\d)")  # Exclusion regex used to detect ID-card-shaped candidates.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid bank card numbers.

        Business logic:
            1. Extract bank-card-like fragments with the candidate regex.
            2. Exclude ID-card-shaped fragments that fail ID validation.
            3. Validate bank card candidates with the Luhn checksum.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: Bank card assessment result.

        Examples:
            >>> TextBankCardAssessor().assess("4111111111111111").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid bank card numbers", "No bank card number detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a bank card candidate is real.

        Business logic:
            1. Remove spaces and hyphens from the candidate.
            2. Reject ID-card-shaped candidates that fail ID validation.
            3. Validate the remaining number with the Luhn checksum.

        Args:
            candidate (str): Bank card candidate to validate.

        Returns:
            bool: Whether the bank card number is valid.

        Examples:
            >>> TextBankCardAssessor().is_valid("4111111111111111")
            True
        """
        compact_candidate = re.sub(r"[ -]", "", candidate)
        if self.id_card_pattern.fullmatch(compact_candidate) and not id_card_validator.is_valid(compact_candidate):  # Reject candidates that look like ID cards but fail ID validation.
            return False
        return luhn.is_valid(compact_candidate)
