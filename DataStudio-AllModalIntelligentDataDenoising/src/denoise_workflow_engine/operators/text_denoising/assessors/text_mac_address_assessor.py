import regex as re

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextMacAddressAssessor(BaseTextAssessor):
    sensitive_type = "mac_address"  # Sensitive information type: MAC address.
    pattern = re.compile(r"(?<![0-9A-Fa-f])(?:[0-9A-Fa-f]{2}([:-]))(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}(?![0-9A-Fa-f])")  # Candidate regex that matches colon-separated and hyphen-separated MAC addresses with a consistent separator.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid MAC addresses.

        Business logic:
            1. Extract MAC-address-like fragments with the candidate regex.
            2. Validate separator consistency and hexadecimal-octet structure.
            3. Return the MAC address assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: MAC address assessment result.

        Examples:
            >>> TextMacAddressAssessor().assess("MAC 00:1A:2B:3C:4D:5E").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid MAC addresses", "No MAC address detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a MAC-address candidate is structurally valid.

        Business logic:
            1. Reject empty candidates or candidates without exactly one supported separator type.
            2. Split the candidate into six octets using the detected separator.
            3. Require each octet to contain exactly two hexadecimal digits.

        Args:
            candidate (str): MAC-address candidate to validate.

        Returns:
            bool: Whether the MAC-address candidate is valid.

        Examples:
            >>> TextMacAddressAssessor().is_valid("00-1A-2B-3C-4D-5E")
            True
        """
        if not candidate:
            return False
        has_colon = ":" in candidate
        has_hyphen = "-" in candidate
        if has_colon == has_hyphen:  # Reject candidates with mixed separators or no separator at all.
            return False
        separator = ":" if has_colon else "-"
        parts = candidate.split(separator)
        if len(parts) != 6:
            return False
        return all(len(part) == 2 and all(char in "0123456789abcdefABCDEF" for char in part) for part in parts)
