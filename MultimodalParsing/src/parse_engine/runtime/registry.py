from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Dict, Type

from parse_engine.operators.base import BaseOperator


class OperatorRegistry:
    def __init__(self) -> None:
        """Initialize an empty operator registry.

        Business logic:
            1. Create a mapping dictionary from operator names to operator classes.
            2. Wait for register to write operator_name values into the mapping.
            3. Provide a unified creation entrypoint for operators declared in workflow config.

        Args:
            None.

        Returns:
            None: The constructor only initializes registry state.

        Examples:
            >>> OperatorRegistry()._operators
            {}"""
        self._operators: Dict[str, Type[BaseOperator]] = {}  # Operator map: store operator classes by snake_case operator_name.

    def register(self, operator_cls: Type[BaseOperator]) -> Type[BaseOperator]:
        """Register an operator class in the name mapping table.

        Business logic:
            1. Validate that operator_name is snake_case.
            2. Register the operator by operator_name so stable business names can be referenced.
            3. Return the original class object so the function can be used as a decorator.

        Args:
            operator_cls: Operator class that inherits from BaseOperator.

        Returns:
            Type[BaseOperator]: The operator class returned unchanged.

        Examples:
            >>> issubclass(BaseOperator, object)
            True"""
        if not inspect.isclass(operator_cls) or not issubclass(operator_cls, BaseOperator):  # Only register BaseOperator subclasses.
            raise ValueError(f"Operator must inherit BaseOperator: {operator_cls}")
        _validate_operator_name(operator_cls.operator_name)
        if operator_cls.operator_name in self._operators:  # Duplicate registry names would make workflow resolution ambiguous and must fail.
            raise ValueError(f"Duplicate operator name: {operator_cls.operator_name}")
        self._operators[operator_cls.operator_name] = operator_cls
        return operator_cls

    def create(self, name: str, params: dict) -> BaseOperator:
        """Create an operator instance by name.

        Business logic:
            1. Look up the operator class corresponding to operator_name in the registry.
            2. When not found, list all available operator names and raise KeyError.
            3. When found, construct and return the operator instance with params.

        Args:
            name: Operator name declared in workflow configuration.
            params: Parameter dictionary passed to the operator constructor.

        Returns:
            BaseOperator: Operator instance created with bound configuration.

        Examples:
            >>> isinstance("pdf_text_extract", str)
            True"""
        if name not in self._operators:  # Provide available names to help fix workflow configuration.
            available = ", ".join(sorted(self._operators))
            raise KeyError(f"Unknown operator '{name}'. Available operators: {available}")
        return self._operators[name](params)


registry = OperatorRegistry()


def _validate_operator_name(operator_name: str) -> None:
    """Validate that an operator registry name is snake_case.

    Business logic:
        1. Accept an operator registry name.
        2. Check snake_case using character-level rules.
        3. Raise ValueError on invalid input to block registration.

    Args:
        operator_name: Operator registry name to validate.

    Returns:
        None: Nothing is returned when validation succeeds.

    Examples:
        >>> _validate_operator_name("pdf_text_extract")
    """
    if (
        not operator_name
        or not operator_name[0].isalpha()
        or not operator_name.islower()
        or any(not (char.islower() or char.isdigit() or char == "_") for char in operator_name)
    ):  # Registry names must be directly usable in workflow config.
        raise ValueError(f"operator_name must be snake_case: {operator_name}")


def register_operator(operator_cls: Type[BaseOperator]) -> Type[BaseOperator]:
    """Register an operator class in the global registry.

    Business logic:
        1. Accept the decorated operator class.
        2. Call global registry.register to write the operator_name mapping.
        3. Return the original class so the decorator does not alter the class definition.

    Args:
        operator_cls: Operator class to register.

    Returns:
        Type[BaseOperator]: Original operator class, registered and not replaced by wrapping.

    Examples:
        >>> callable(register_operator)
        True"""
    return registry.register(operator_cls)


def load_custom_operators(operator_refs: list[str] | None, base_dir: Path | None = None) -> None:
    """Load and register user-defined parsing operators.

    Business logic:
        1. Traverse file or module references in workflow custom_operators.
        2. Import modules and scan for operator classes inheriting from BaseOperator.
        3. Register them in the global registry so workflow steps can reference them.

    Args:
        operator_refs (list[str] | None): List of user-defined operator files or modules.
        base_dir (Path | None): Base directory for resolving relative paths.

    Returns:
        None: The global registry is modified directly.

    Examples:
        >>> load_custom_operators([])
    """
    for operator_ref in operator_refs or []:  # Load files or modules one by one.
        module = _load_operator_module(operator_ref, base_dir)
        operator_classes = [
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls is not BaseOperator and issubclass(cls, BaseOperator) and cls.__module__ == module.__name__
        ]
        if not operator_classes:  # The module must provide at least one valid operator class.
            raise ValueError(f"No BaseOperator subclass found in custom operator: {operator_ref}")
        for operator_cls in operator_classes:  # Register all valid operators in the module.
            if operator_cls.operator_name not in registry._operators:  # Avoid duplicate registration during repeated validate calls.
                registry.register(operator_cls)


def _load_operator_module(operator_ref: str, base_dir: Path | None = None) -> Any:
    """Import a user-defined parsing operator module.

    Business logic:
        1. Decide whether the configured value points to a Python file.
        2. Load file paths via importlib.util.
        3. Import non-file paths as Python module names.

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
    if not candidate.is_absolute():  # Resolve relative to the workflow directory.
        candidate = (base_dir or Path.cwd()) / candidate
    if operator_ref.endswith(".py") or candidate.exists():  # Import by file path.
        if not candidate.exists():  # Fail when the declared file does not exist.
            raise FileNotFoundError(f"Custom operator file not found: {candidate}")
        module_name = f"parse_custom_operator_{abs(hash(str(candidate)))}"
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:  # Missing loader means the module cannot be imported.
            raise ImportError(f"Cannot import custom operator file: {candidate}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(operator_ref)
