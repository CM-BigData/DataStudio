import regex as re

import phonenumbers

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextPhoneAssessor(BaseTextAssessor):
    sensitive_type = "phone"  # Sensitive information type: mobile phone number.
    pattern = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")  # Candidate regex that matches Chinese mobile phone numbers.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid mobile phone numbers.

        Business logic:
            1. Extract phone-like fragments with the mobile regex.
            2. Validate each fragment with `phonenumbers` for China.
            3. Return the phone assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: Phone assessment result.

        Examples:
            >>> TextPhoneAssessor().assess("13800138000").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid phone numbers", "No phone number detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a phone candidate is a real mobile number.

        Business logic:
            1. Parse the candidate with China as the default region.
            2. Check whether the number is possible.
            3. Check whether the number is valid.

        Args:
            candidate (str): Phone candidate to validate.

        Returns:
            bool: Whether the phone number is valid.

        Examples:
            >>> TextPhoneAssessor().is_valid("13800138000")
            True
        """
        try:
            number = phonenumbers.parse(candidate, "CN")
        except phonenumbers.NumberParseException:
            return False
        return phonenumbers.is_possible_number(number) and phonenumbers.is_valid_number(number)
