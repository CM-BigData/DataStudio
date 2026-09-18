from importlib import import_module

_EXPORTS = {
    "ImageDenoiseOperator": "denoise_workflow_engine.operators.image_denoising.operator",
    "ImageDecodeOperator": "denoise_workflow_engine.operators.image_denoising.decode",
    "ImageMetaOperator": "denoise_workflow_engine.operators.image_denoising.metadata",
    "BlurDetectOperator": "denoise_workflow_engine.operators.image_denoising.quality",
    "ExposureDetectOperator": "denoise_workflow_engine.operators.image_denoising.quality",
    "NoiseEstimateOperator": "denoise_workflow_engine.operators.image_denoising.quality",
    "ReferenceImageQualityOperator": "denoise_workflow_engine.operators.image_denoising.quality",
    "SubjectCompletenessOperator": "denoise_workflow_engine.operators.image_denoising.quality",
    "VLMImageQualityOperator": "denoise_workflow_engine.operators.image_denoising.quality",
    "QRCodeDetectOperator": "denoise_workflow_engine.operators.image_denoising.signals",
    "WatermarkDetectOperator": "denoise_workflow_engine.operators.image_denoising.signals",
    "LogoDetectOperator": "denoise_workflow_engine.operators.image_denoising.signals",
    "ImageSafetyOperator": "denoise_workflow_engine.operators.image_denoising.safety",
    "ImageRepairOperator": "denoise_workflow_engine.operators.image_denoising.repair",
    "ImageQualityScorer": "denoise_workflow_engine.operators.image_denoising.scoring",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> object:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    return getattr(module, name)
