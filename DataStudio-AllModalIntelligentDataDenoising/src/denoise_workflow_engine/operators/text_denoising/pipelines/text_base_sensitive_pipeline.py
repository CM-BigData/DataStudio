from __future__ import annotations

from dataclasses import dataclass

from denoise_workflow_engine.operators.text_denoising.assessors import BaseTextAssessor, TextAssessment
from denoise_workflow_engine.operators.text_denoising.governors import BaseTextGovernor


@dataclass(frozen=True)
class TextSensitivePipelineResult:
    text: str  # Final governed text produced by the pipeline.
    assessments: list[TextAssessment]  # Ordered list of sensitive-information assessments produced during execution.

    @property
    def hit_types(self) -> list[str]:
        """Return the sensitive-information types detected by the pipeline.

        Business logic:
            1. Iterate through the pipeline assessment list.
            2. Filter results whose `detected` field is `True`.
            3. Return sensitive types in pipeline execution order.

        Args:
            None: This property takes no input parameters.

        Returns:
            list[str]: List of detected sensitive-information types.

        Examples:
            >>> TextSensitivePipelineResult("", []).hit_types
            []
        """
        return [assessment.sensitive_type for assessment in self.assessments if assessment.detected]


class BaseTextSensitivePipeline:
    steps: tuple[tuple[BaseTextAssessor, BaseTextGovernor], ...] = ()  # Ordered assessor/governor pairs executed by the pipeline.

    def __init__(self) -> None:
        """Initialize the text-sensitive-information pipeline.

        Business logic:
            1. Read the step list declared by the concrete pipeline.
            2. Validate that assessor and governor types match.
            3. Keep the execution steps reusable.

        Args:
            None: This constructor does not take input parameters.

        Returns:
            None: Initialization results are stored on the instance.

        Examples:
            >>> BaseTextSensitivePipeline().steps
            ()
        """
        self._validate_steps()

    def run(self, text: str) -> TextSensitivePipelineResult:
        """Run the text-sensitive-information pipeline.

        Business logic:
            1. Execute each assessor in declared order.
            2. Pass each assessment to its paired governor to redact text.
            3. Return the governed text together with all assessments.

        Args:
            text (str): Text to process.

        Returns:
            TextSensitivePipelineResult: Pipeline execution result.

        Examples:
            >>> BaseTextSensitivePipeline().run("abc").text
            'abc'
        """
        governed = text
        assessments = []
        for assessor, governor in self.steps:  # Run each assessment/governance pair in declared order.
            assessment = assessor.assess(governed)
            assessments.append(assessment)
            governed = governor.govern(governed, assessment)
        return TextSensitivePipelineResult(text=governed, assessments=assessments)

    def _validate_steps(self) -> None:
        """Validate text-sensitive-information pipeline steps.

        Business logic:
            1. Iterate through assessor/governor pairs.
            2. Compare their `sensitive_type` values.
            3. Raise `ValueError` when the types do not match.

        Args:
            None: This method does not take input parameters.

        Returns:
            None: Validation succeeds silently.

        Examples:
            >>> BaseTextSensitivePipeline()._validate_steps()
            None
        """
        for assessor, governor in self.steps:  # Each step must pair the same sensitive-information type.
            if assessor.sensitive_type != governor.sensitive_type:  # Mismatched types would cause incorrect redaction.
                raise ValueError(f"Text-sensitive pipeline type mismatch: {assessor.sensitive_type} != {governor.sensitive_type}")
