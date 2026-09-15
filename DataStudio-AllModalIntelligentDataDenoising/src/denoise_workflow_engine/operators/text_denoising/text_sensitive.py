from denoise_workflow_engine.operators.text_denoising.text_base_sensitive_operator import BaseTextSensitiveOperator
from denoise_workflow_engine.operators.text_denoising.pipelines import TextSensitiveDetectPipeline


class TextSensitiveDetectOperator(BaseTextSensitiveOperator):
    operator_name: str = "text_sensitive_detect"  # Operator identifier used by workflow configs and the registry.
    pipeline = TextSensitiveDetectPipeline()  # Text-sensitive-information pipeline that performs concrete detection and governance steps.
