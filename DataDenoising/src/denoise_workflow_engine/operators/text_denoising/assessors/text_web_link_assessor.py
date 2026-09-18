import regex as re

import validators

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextWebLinkAssessor(BaseTextAssessor):
    sensitive_type = "url"  # Sensitive information type: URL.
    pattern = re.compile(r"(?i)\bhttps?://[^\s<>'\"]+")  # Candidate regex that matches HTTP and HTTPS links.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid URLs.

        Business logic:
            1. Extract URL-like fragments with the candidate regex.
            2. Validate HTTP or HTTPS URLs with `validators`.
            3. Return the URL assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: URL assessment result.

        Examples:
            >>> TextWebLinkAssessor().assess("https://example.com").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid URLs", "No URL detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a URL candidate is well-formed.

        Business logic:
            1. Accept a URL candidate string.
            2. Confirm that the scheme is HTTP or HTTPS.
            3. Validate the URL with `validators`.

        Args:
            candidate (str): URL candidate to validate.

        Returns:
            bool: Whether the URL is valid.

        Examples:
            >>> TextWebLinkAssessor().is_valid("https://example.com")
            True
        """
        return bool(validators.url(candidate) and candidate.lower().startswith(("http://", "https://")))
