from importlib import import_module

_EXPORTS = {
    "ImageSynthesisOperator": "synthesis_engine.operators.image_synthesis.operator",
    "MultimodalSynthesisOperator": "synthesis_engine.operators.multimodal_synthesis.operator",
    "QuestionAugmentationSynthesisOperator": "synthesis_engine.operators.question_augmentation_synthesis.operator",
    "QuestionDecompositionSynthesisOperator": "synthesis_engine.operators.question_decomposition_synthesis.operator",
    "StructuredSynthesisOperator": "synthesis_engine.operators.structured_synthesis.operator",
    "SynonymReplacementSynthesisOperator": "synthesis_engine.operators.synonym_replacement_synthesis.operator",
    "TableQaSynthesisOperator": "synthesis_engine.operators.table_qa_synthesis.operator",
    "TextQaSynthesisOperator": "synthesis_engine.operators.text_qa_synthesis.operator",
    "TextSynthesisOperator": "synthesis_engine.operators.text_synthesis.operator",
}

_MODULES = {name: import_module(module_name) for name, module_name in _EXPORTS.items()}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> object:
    module = _MODULES.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(module, name)
