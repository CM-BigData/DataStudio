from denoise_workflow_engine.operators.text_denoising.assessors import (
    TextBankCardAssessor,
    TextEmailAssessor,
    TextIdCardAssessor,
    TextIPAssessor,
    TextLandlineAssessor,
    TextMacAddressAssessor,
    TextPhoneAssessor,
    TextQQAssessor,
    TextWebLinkAssessor,
    TextWechatAssessor,
)
from denoise_workflow_engine.operators.text_denoising.governors import (
    TextBankCardGovernor,
    TextEmailGovernor,
    TextIdCardGovernor,
    TextIPGovernor,
    TextLandlineGovernor,
    TextMacAddressGovernor,
    TextPhoneGovernor,
    TextQQGovernor,
    TextWebLinkGovernor,
    TextWechatGovernor,
)
from denoise_workflow_engine.operators.text_denoising.pipelines.text_base_sensitive_pipeline import BaseTextSensitivePipeline


class TextSensitiveDetectPipeline(BaseTextSensitivePipeline):
    steps = (  # Detection/governance order that preserves the current text-redaction behavior.
        (TextWebLinkAssessor(), TextWebLinkGovernor()),
        (TextEmailAssessor(), TextEmailGovernor()),
        (TextPhoneAssessor(), TextPhoneGovernor()),
        (TextLandlineAssessor(), TextLandlineGovernor()),
        (TextMacAddressAssessor(), TextMacAddressGovernor()),
        (TextIPAssessor(), TextIPGovernor()),
        (TextQQAssessor(), TextQQGovernor()),
        (TextWechatAssessor(), TextWechatGovernor()),
        (TextIdCardAssessor(), TextIdCardGovernor()),
        (TextBankCardAssessor(), TextBankCardGovernor()),
    )
