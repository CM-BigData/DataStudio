import regex as re

from denoise_workflow_engine.operators.text_denoising.assessors.text_base_assessor import TextAssessment
from denoise_workflow_engine.operators.text_denoising.assessors.text_phone_assessor import TextPhoneAssessor


class TextLandlineAssessor(TextPhoneAssessor):
    sensitive_type = "landline"  # Sensitive information type: landline number.
    pattern = re.compile(r"(?<![\d:：])(?:\+?86[- ]?)?(?:0\d{2,3}[- ]?)?\d{7,8}(?!\d)")  # Candidate regex that matches Chinese landline numbers.

    def assess(self, text: str) -> TextAssessment:
        """Assess whether the text contains valid landline numbers.

        Business logic:
            1. Extract landline-like fragments with the candidate regex.
            2. Reuse phone validation logic to verify the candidates.
            3. Return the landline assessment result.

        Args:
            text (str): Text to assess.

        Returns:
            TextAssessment: Landline assessment result.

        Examples:
            >>> TextLandlineAssessor().assess("01012345678").sensitive_type
            'landline'
        """
        candidates = self._extract_valid_candidates(text)
        return self._build_result(candidates, "Contains valid landline numbers", "No landline number detected")
