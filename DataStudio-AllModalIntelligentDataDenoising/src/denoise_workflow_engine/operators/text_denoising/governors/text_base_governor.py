from denoise_workflow_engine.operators.text_denoising.assessors import TextAssessment


class BaseTextGovernor:
    sensitive_type: str = ""  # Sensitive information type declared by the concrete governor.
    replacement: str = ""  # Redaction token written into the governed text.

    def govern(self, text: str, assessment: TextAssessment) -> str:
        """Redact sensitive-information candidates from text.

        Business logic:
            1. Verify that the assessment type matches the governor type.
            2. Iterate through candidates already confirmed as valid.
            3. Replace each candidate with the governor's redaction token.

        Args:
            text (str): Text to govern.
            assessment (TextAssessment): Sensitive-information assessment result.

        Returns:
            str: Governed text.

        Examples:
            >>> from denoise_workflow_engine.operators.text_denoising.assessors import TextAssessment
            >>> BaseTextGovernor().govern("abc", TextAssessment("", False, [], 1.0, ""))
            'abc'
        """
        if assessment.sensitive_type != self.sensitive_type:  # Reject mismatched assessment/governor pairs.
            raise ValueError(f"Sensitive type mismatch: {assessment.sensitive_type} != {self.sensitive_type}")
        if not assessment.detected:  # Preserve the original text when nothing sensitive was detected.
            return text
        governed = text
        for candidate in assessment.candidates:  # Replace only candidates confirmed by the assessment layer.
            governed = governed.replace(candidate, self.replacement)
        return governed
