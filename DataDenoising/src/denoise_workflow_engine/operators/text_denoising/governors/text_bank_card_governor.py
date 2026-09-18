from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextBankCardGovernor(BaseTextGovernor):
    sensitive_type = "bank_card"  # Sensitive information type: bank card number.
    replacement = "[BANK_CARD]"  # Redaction token used for bank card numbers.
