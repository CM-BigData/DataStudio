from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextEmailGovernor(BaseTextGovernor):
    sensitive_type = "email"  # Sensitive information type: email address.
    replacement = "[EMAIL]"  # Redaction token used for email addresses.
