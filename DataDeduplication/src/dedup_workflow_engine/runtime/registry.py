from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Type

from dedup_workflow_engine.operators import AudioDedupOperator, ImageDedupOperator, TextDedupOperator
from dedup_workflow_engine.operators.base import BaseOperator


class OperatorRegistry:
    def __init__(self) -> None:
        """Create a workflow operator registry.

        Business logic:
            1. Initialize an empty dictionary.
            2. Use operator_name as the key.
            3. Store BaseOperator subclasses so the executor can instantiate them.

        Args:
            None: This initializer does not accept business parameters.

        Returns:
            None: This initializer does not return a value.

        Examples:
            >>> registry = OperatorRegistry()
            >>> isinstance(registry._operators, dict)
            True
        """
        self._operators: dict[str, Type[BaseOperator]] = {}  # Workflow config: instantiable operator classes keyed by operator_name.

    def register(self, operator_cls: Type[BaseOperator]) -> None:
        """Register a workflow operator class.

        Business logic:
            1. Read the operator class's operator_name.
            2. Map the name to the operator class.
            3. Allow later workflow steps to create instances by that name.

        Args:
            operator_cls (Type[BaseOperator]): Operator class to register.

        Returns:
            None: Registration updates the internal dictionary and nothing is returned.

        Examples:
            >>> registry = OperatorRegistry()
            >>> registry.register(BaseOperator)  # doctest: +SKIP
        """
        if not inspect.isclass(operator_cls) or not issubclass(operator_cls, BaseOperator):  # Only BaseOperator subclasses can be registered.
            raise ValueError(f"Operator must inherit BaseOperator: {operator_cls}")
        _validate_operator_name(operator_cls.operator_name)
        if operator_cls.operator_name in self._operators:  # Duplicate names make workflow resolution ambiguous.
            raise ValueError(f"Duplicate operator name: {operator_cls.operator_name}")
        self._operators[operator_cls.operator_name] = operator_cls

    def create(self, operator_name: str, config: dict[str, Any]) -> BaseOperator:
        """Create an operator instance by the name used in workflow config.

        Business logic:
            1. Validate that operator_name has been registered.
            2. When it is missing, report all known operator names to help debug config errors.
            3. When it exists, create the operator instance with step params as config.

        Args:
            operator_name (str): Registered operator name referenced by the workflow step.
            config (dict[str, Any]): Operator parameters for the current step.

        Returns:
            BaseOperator: Configured operator instance.

        Raises:
            KeyError: Raised when the workflow references an unknown operator name.

        Examples:
            >>> OperatorRegistry().create("missing", {})
            Traceback (most recent call last):
            ...
            KeyError: "Unknown operator 'missing'. Known operators: "
        """
        if operator_name not in self._operators:  # Report known names so workflow authors can fix typos quickly.
            known = ", ".join(sorted(self._operators))
            raise KeyError(f"Unknown operator '{operator_name}'. Known operators: {known}")
        return self._operators[operator_name](config=config)


def build_default_registry() -> OperatorRegistry:
    """Build the default registry of built-in end-to-end deduplication operators.

    Business logic:
        1. Create an empty OperatorRegistry.
        2. Register only public text, image, and audio end-to-end operators.
        3. Return the registry that the executor can use directly.

    Args:
        None: The default registry does not need external parameters.

    Returns:
        OperatorRegistry: Registry containing public built-in operators.

    Examples:
        >>> registry = build_default_registry()
        >>> registry.create("text_dedup", {})
        TextDedupOperator(...)  # doctest: +SKIP
    """
    registry = OperatorRegistry()
    for operator_cls in [  # Keep public operator registration order deterministic.
        TextDedupOperator,
        ImageDedupOperator,
        AudioDedupOperator,
    ]:
        registry.register(operator_cls)
    return registry


def load_custom_operators(registry: OperatorRegistry, operator_refs: list[str] | None, base_dir: Path | None = None) -> None:
    """Load and register user-defined deduplication operators.

    Business logic:
        1. Iterate over file or module references from workflow custom_operators.
        2. Import each module and scan for operator classes inheriting from BaseOperator.
        3. Register them into the provided registry so workflow steps can reference them.

    Args:
        registry (OperatorRegistry): Operator registry used by the current workflow.
        operator_refs (list[str] | None): List of custom operator files or modules.
        base_dir (Path | None): Base directory for resolving relative paths.

    Returns:
        None: The passed-in registry is modified in place.

    Examples:
        >>> load_custom_operators(OperatorRegistry(), [])
    """
    for operator_ref in operator_refs or []:  # Load each custom operator file or module.
        module = _load_operator_module(operator_ref, base_dir)
        operator_classes = [
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls is not BaseOperator and issubclass(cls, BaseOperator) and cls.__module__ == module.__name__
        ]
        if not operator_classes:  # Custom operator modules must expose at least one concrete operator class.
            raise ValueError(f"No BaseOperator subclass found in custom operator: {operator_ref}")
        for operator_cls in operator_classes:  # Register all concrete operators exported by the module.
            if operator_cls.operator_name not in registry._operators:  # Avoid duplicate registration during validate/run tests.
                registry.register(operator_cls)


def _load_operator_module(operator_ref: str, base_dir: Path | None = None) -> Any:
    """Import a user-defined deduplication operator module.

    Business logic:
        1. Decide whether the config value points to a Python file.
        2. Load file paths with importlib.util.
        3. Import non-file values as Python module names.

    Args:
        operator_ref (str): Python file path or module path.
        base_dir (Path | None): Base directory for resolving relative paths.

    Returns:
        Any: Imported module object.

    Examples:
        >>> callable(_load_operator_module)
        True
    """
    candidate = Path(operator_ref)
    if not candidate.is_absolute():  # Relative custom paths are resolved from the workflow directory.
        candidate = (base_dir or Path.cwd()) / candidate
    if operator_ref.endswith(".py") or candidate.exists():  # Existing file references are imported by path.
        if not candidate.exists():  # Missing declared files fail fast during validation.
            raise FileNotFoundError(f"Custom operator file not found: {candidate}")
        module_name = f"dedup_custom_operator_{abs(hash(str(candidate)))}"
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:  # Import specs without loaders cannot execute modules.
            raise ImportError(f"Cannot import custom operator file: {candidate}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(operator_ref)


def _validate_operator_name(operator_name: str) -> None:
    """Validate the operator registration name format.

    Business logic:
        1. Accept operator_name as input.
        2. Validate snake_case using the character rules.
        3. Raise ValueError when the name is invalid.

    Args:
        operator_name (str): Operator registration name to validate.

    Returns:
        None: Nothing is returned when validation succeeds.

    Examples:
        >>> _validate_operator_name("text_normalize_for_dedup")
    """
    if (
        not operator_name
        or not operator_name[0].isalpha()
        or not operator_name.islower()
        or any(not (char.islower() or char.isdigit() or char == "_") for char in operator_name)
    ):  # Workflow operator names must be snake_case only.
        raise ValueError(f"operator_name must be snake_case: {operator_name}")
