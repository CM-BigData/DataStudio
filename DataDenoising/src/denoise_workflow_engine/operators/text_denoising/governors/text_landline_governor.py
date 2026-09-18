from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextLandlineGovernor(BaseTextGovernor):
    sensitive_type = "landline"  # Sensitive information type: landline number.
    replacement = "[LANDLINE]"  # Redaction token used for landline numbers.
