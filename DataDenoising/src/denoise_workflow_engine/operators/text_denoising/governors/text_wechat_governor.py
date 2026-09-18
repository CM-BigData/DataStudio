from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextWechatGovernor(BaseTextGovernor):
    sensitive_type = "wechat"  # Sensitive information type: WeChat identifier.
    replacement = "[WECHAT]"  # Redaction token used for WeChat identifiers.
