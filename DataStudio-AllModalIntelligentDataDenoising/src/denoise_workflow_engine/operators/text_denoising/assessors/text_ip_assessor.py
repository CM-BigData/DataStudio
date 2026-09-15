import ipaddress
import regex as re

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextIPAssessor(BaseTextAssessor):
    sensitive_type = "ip"  # Sensitive information type: IP address.
    pattern = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")  # Candidate regex that matches IPv4 addresses.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid IP addresses.

        Business logic:
            1. Extract IP-like fragments with the candidate regex.
            2. Validate each fragment with `ipaddress`.
            3. Return the IP assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: IP assessment result.

        Examples:
            >>> TextIPAssessor().assess("192.168.1.1").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid IP addresses", "No IP address detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether an IP candidate is real.

        Business logic:
            1. Accept an IP candidate string.
            2. Parse the candidate with `ipaddress`.
            3. Return whether the IP address is valid.

        Args:
            candidate (str): IP candidate to validate.

        Returns:
            bool: Whether the IP address is valid.

        Examples:
            >>> TextIPAssessor().is_valid("192.168.1.1")
            True
        """
        try:
            ipaddress.ip_address(candidate)
            return True
        except ValueError:
            return False
