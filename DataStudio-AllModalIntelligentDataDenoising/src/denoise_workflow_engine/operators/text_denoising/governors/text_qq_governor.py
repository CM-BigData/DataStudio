from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextQQGovernor(BaseTextGovernor):
    sensitive_type = "qq"  # Sensitive information type: QQ account number.
    replacement = "[QQ]"  # Redaction token used for QQ account identifiers.
