from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextIdCardGovernor(BaseTextGovernor):
    sensitive_type = "id_card"  # Sensitive information type: identity card number.
    replacement = "[ID_CARD]"  # Redaction token used for ID card numbers.
