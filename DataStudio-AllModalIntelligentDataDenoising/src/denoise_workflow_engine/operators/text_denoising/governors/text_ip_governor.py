from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextIPGovernor(BaseTextGovernor):
    sensitive_type = "ip"  # Sensitive information type: IP address.
    replacement = "[IP]"  # Redaction token used for IP addresses.
