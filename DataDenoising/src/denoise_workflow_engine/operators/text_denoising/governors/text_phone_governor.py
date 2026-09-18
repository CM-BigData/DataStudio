from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextPhoneGovernor(BaseTextGovernor):
    sensitive_type = "phone"  # Sensitive information type: mobile phone number.
    replacement = "[PHONE]"  # Redaction token used for phone numbers.
