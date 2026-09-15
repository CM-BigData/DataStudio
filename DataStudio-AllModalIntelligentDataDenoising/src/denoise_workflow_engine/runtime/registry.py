from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Sequence, Type

from denoise_workflow_engine.operators.base import BaseOperator
from denoise_workflow_engine.operators.auto_denoising import AutoDenoiseOperator
from denoise_workflow_engine.operators.image_denoising import ImageDenoiseOperator
from denoise_workflow_engine.operators.image_text_pair_denoising import ImageTextPairDenoiseOperator
from denoise_workflow_engine.operators.text_denoising import TextDenoiseOperator
from denoise_workflow_engine.operators.video_denoising import VideoDenoiseOperator
from denoise_workflow_engine.runtime.loader import resolve_path


class OperatorRegistry:
    def __init__(self) -> None:
        """Create an empty operator registry.

        Business logic:
            1. Initialize the internal operator mapping.
            2. Keep workflow-facing operator classes addressable by name.
            3. Avoid any expensive loading during construction.

        Args:
                None: This constructor does not take input parameters.

        Returns:
            None: The constructor initializes the registry in place.

        Examples:
            >>> isinstance(OperatorRegistry(), OperatorRegistry)
            True
        """
        self._operators: dict[str, Type[BaseOperator]] = {}  # Operator registry keyed by operator_name.

    def register(self, operator_cls: Type[BaseOperator]) -> None:
        """Register an operator class in the registry.

        Business logic:
            1. Validate that the object is a BaseOperator subclass.
            2. Validate the operator registration name.
            3. Reject duplicate names before storing the class.

        Args:
                operator_cls (Type[BaseOperator]): Operator class.

        Returns:
            None: The method mutates the registry in place.

        Examples:
            >>> callable(OperatorRegistry().register)
            True
        """
        if not inspect.isclass(operator_cls) or not issubclass(operator_cls, BaseOperator):  # Reject non-BaseOperator subclasses during registration.
            raise ValueError(f"Operator must inherit BaseOperator: {operator_cls}")
        _validate_operator_name(operator_cls.operator_name)
        if operator_cls.operator_name in self._operators:  # Duplicate names would make workflow operator resolution ambiguous.
            raise ValueError(f"Duplicate operator name: {operator_cls.operator_name}")
        self._operators[operator_cls.operator_name] = operator_cls

    def create(self, operator_name: str, config: dict[str, Any]) -> BaseOperator:
        """Create an operator instance by registration name.

        Business logic:
            1. Check whether the requested operator name is registered.
            2. Provide a helpful error listing known operators when it is missing.
            3. Instantiate the operator with the provided config.

        Args:
                operator_name (str): Operator registration name.
                config (dict[str, Any]): Operator configuration dictionary.

        Returns:
            BaseOperator: Instantiated operator.

        Examples:
            >>> callable(OperatorRegistry().create)
            True
        """
        if operator_name not in self._operators:  # List known operators to help debug workflow config errors.
            known = ", ".join(sorted(self._operators))
            raise KeyError(f"Unknown operator '{operator_name}'. Known operators: {known}")
        return self._operators[operator_name](config=config)


def build_default_registry(
    custom_operators: list[str] | None = None,
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> OperatorRegistry:
    """Build a registry populated with built-in project operators.

    Business logic:
        1. Create a fresh registry.
        2. Register all built-in operator classes.
        3. Optionally load and register custom operator modules.

    Args:
        custom_operators (list[str] | None): Custom operator files or module paths.
        base_dir (Path | None): Base directory for resolving custom operator paths.

    Returns:
        OperatorRegistry: Populated operator registry.

    Examples:
        >>> isinstance(build_default_registry([]), OperatorRegistry)
        True
    """
    registry = OperatorRegistry()  # Registry used to create executable operator instances by name.
    for operator_cls in [
        TextDenoiseOperator,
        ImageDenoiseOperator,
        ImageTextPairDenoiseOperator,
        VideoDenoiseOperator,
        AutoDenoiseOperator,
    ]:
        registry.register(operator_cls)
    if custom_operators:  # Register custom operators only when configured by the user.
        for operator_ref in custom_operators:  # Load each custom file or module one by one.
            load_custom_operators(registry, operator_ref, base_dir=base_dir, allowed_roots=allowed_roots)
    return registry


def load_custom_operators(
    registry: OperatorRegistry,
    operator_ref: str,
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> None:
    """Load and register user-defined operators.

    Business logic:
        1. Import the user operator module from a file path or Python module path.
        2. Scan the module for concrete BaseOperator subclasses.
        3. Register every valid class and reject empty or invalid modules.

    Args:
        registry (OperatorRegistry): Target operator registry.
        operator_ref (str): Python file path or module path supplied by the user.
        base_dir (Path | None): Base directory for resolving relative paths.

    Returns:
        None: The function registers operators into `registry` in place.

    Examples:
        >>> callable(load_custom_operators)
        True
    """
    module = _load_operator_module(operator_ref, base_dir, allowed_roots=allowed_roots)
    operator_classes = [
        cls
        for _, cls in inspect.getmembers(module, inspect.isclass)
        if cls is not BaseOperator and issubclass(cls, BaseOperator) and cls.__module__ == module.__name__
    ]
    if not operator_classes:  # A custom module must provide at least one valid operator class.
        raise ValueError(f"No BaseOperator subclass found in custom operator: {operator_ref}")
    for operator_cls in operator_classes:  # Register every valid custom operator class found in the module.
        registry.register(operator_cls)


def _load_operator_module(
    operator_ref: str,
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> Any:
    """Import a user-defined operator module.

    Business logic:
        1. Detect whether the reference points to a Python file path.
        2. Import file paths with `importlib.util`.
        3. Import non-file references as standard Python modules.

    Args:
        operator_ref (str): Python file path or module path.
        base_dir (Path | None): Base directory for resolving relative paths.

    Returns:
        Any: Imported Python module object.

    Examples:
        >>> callable(_load_operator_module)
        True
    """
    candidate = Path(operator_ref)
    if not candidate.is_absolute():  # Resolve relative file paths from the workflow base directory.
        candidate = (base_dir or Path.cwd()) / candidate
    if operator_ref.endswith(".py") or candidate.exists():  # Import file references directly from their path.
        candidate = resolve_path(
            candidate,
            allowed_roots=allowed_roots,
            name="custom operator file",
        )
        if not candidate.exists():  # Fail when the declared custom operator file is missing.
            raise FileNotFoundError(f"Custom operator file not found: {candidate}")
        module_name = f"denoise_custom_operator_{abs(hash(str(candidate)))}"
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:  # Abort when import metadata cannot be constructed.
            raise ImportError(f"Cannot import custom operator file: {candidate}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(operator_ref)


def _validate_operator_name(operator_name: str) -> None:
    """Validate the operator registration name format.

    Business logic:
        1. Read the declared operator registration name.
        2. Check whether it follows snake_case character rules.
        3. Raise an error to block registration when the name is invalid.

    Args:
            operator_name (str): Operator registration name.

    Returns:
        None: Validation succeeds silently.

    Examples:
        >>> _validate_operator_name("text_sensitive_detect")
    """
    if (
        not operator_name
        or not operator_name[0].isalpha()
        or not operator_name.islower()
        or any(not (char.islower() or char.isdigit() or char == "_") for char in operator_name)
    ):  # Workflow configurations may reference only snake_case operator names.
        raise ValueError(f"operator_name must be snake_case: {operator_name}")
