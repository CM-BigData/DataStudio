import regex as re

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import BaseTextAssessor, TextAssessment


class TextWechatAssessor(BaseTextAssessor):
    sensitive_type = "wechat"  # Sensitive information type: WeChat identifier.
    pattern = re.compile(r"(?:wechat|wx|we_chat)\s*[:：]?\s*[A-Za-z][-_A-Za-z0-9]{5,19}", re.I)  # Candidate regex that matches WeChat IDs with context keywords.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains WeChat identifiers.

        Business logic:
            1. Extract WeChat-like fragments with the candidate regex.
            2. Confirm candidates through the contextual keyword pattern.
            3. Return the WeChat assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: WeChat assessment result.

        Examples:
            >>> TextWechatAssessor().assess("wechat abcdef").detected
            True
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains WeChat identifiers", "No WeChat identifier detected")

    def is_valid(self, candidate: str) -> bool:
        """Validate whether a WeChat candidate is acceptable.

        Business logic:
            1. Accept a WeChat candidate that already includes contextual keywords.
            2. Rely on the regex to constrain the leading character and length.
            3. Return that the candidate is valid.

        Args:
            candidate (str): WeChat candidate text.

        Returns:
            bool: Whether the WeChat candidate is valid.

        Examples:
            >>> TextWechatAssessor().is_valid("wechat abcdef")
            True
        """
        return True
