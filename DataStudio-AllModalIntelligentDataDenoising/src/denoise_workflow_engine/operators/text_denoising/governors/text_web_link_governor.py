from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextWebLinkGovernor(BaseTextGovernor):
    sensitive_type = "url"  # Sensitive information type: URL.
    replacement = "[URL]"  # Redaction token used for URLs.
