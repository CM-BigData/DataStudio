from denoise_workflow_engine.operators.text_denoising.governors.text_base_governor import BaseTextGovernor


class TextMacAddressGovernor(BaseTextGovernor):
    sensitive_type = "mac_address"  # Sensitive information type: MAC address.
    replacement = "[MAC_ADDRESS]"  # Redaction token used for MAC addresses.
