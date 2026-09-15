from importlib import import_module

_EXPORTS = {
    "TextDatasetEvalOperator": "quality_eval.operators.text_dataset_eval.operator",
    "ImageDatasetEvalOperator": "quality_eval.operators.image_dataset_eval.operator",
    "AudioDatasetEvalOperator": "quality_eval.operators.audio_dataset_eval.operator",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> object:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    return getattr(module, name)

def load_builtin_operators() -> None:
    """Import built-in workflow-facing operators for registry side effects.

    Business logic:
        1. Iterate through the stable built-in operator modules.
        2. Import each module once so decorator registration runs.
        3. Keep operator registration explicit for command-line and tests without forcing package-level cycles.

    Args:
        None.

    Returns:
        None: The registry is updated by module import side effects.

    Examples:
        >>> load_builtin_operators()
    """
    for module_name in dict.fromkeys(_EXPORTS.values()):
        import_module(module_name)
