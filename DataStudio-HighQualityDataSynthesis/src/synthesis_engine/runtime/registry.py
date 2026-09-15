from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any
from typing import Dict, Type

from synthesis_engine.operators.base import BaseOperator


class OperatorRegistry:
    def __init__(self) -> None:
        """Initialize the operator registry

        Business logic:
            1. Create the internal mapping from names to operator classes
            2. Wait for module imports to register concrete operators
            3. Provide a lookup source for later create calls

        Args:
            None.

        Returns:
            None: Initializers do not return data.

        Examples:
            >>> OperatorRegistry()._operators
            {}
        """
        self._operators: Dict[str, Type[BaseOperator]] = {}  # Operator mapping keyed by snake_case operator_name.

    def register(self, operator_cls: Type[BaseOperator]) -> Type[BaseOperator]:
        """Register an operator class

        Business logic:
            1. Validate that operator_name is snake_case
            2. Register the operator under operator_name
            3. Return the original class to support decorator usage

        Args:
            operator_cls (Type[BaseOperator]): Operator class to register.

        Returns:
            Type[BaseOperator]: Original operator class.

        Examples:
            >>> callable(OperatorRegistry().register)
            True
        """
        if not inspect.isclass(operator_cls) or not issubclass(operator_cls, BaseOperator):  # Reject classes that do not inherit from BaseOperator.
            raise ValueError(f"Operator must inherit BaseOperator: {operator_cls}")
        _validate_operator_name(operator_cls.operator_name)
        if operator_cls.operator_name in self._operators:  # Duplicate names would make workflow resolution ambiguous.
            raise ValueError(f"Duplicate operator name: {operator_cls.operator_name}")
        self._operators[operator_cls.operator_name] = operator_cls
        return operator_cls

    def create(self, name: str, params: dict) -> BaseOperator:
        """Create an operator instance by name

        Business logic:
            1. Look up the operator class in the registry
            2. Raise an error listing available names when it is missing
            3. Instantiate the class with params when found

        Args:
            name (str): operator_name。
            params (dict): Operator configuration parameters.

        Returns:
            BaseOperator: Created operator instance.

        Examples:
            >>> isinstance("text_llm_synthesis", str)
            True
        """
        if name not in self._operators:  # Expose available names when an operator is not registered.
            available = ", ".join(sorted(self._operators))
            raise KeyError(f"Unknown operator '{name}'. Available operators: {available}")
        return self._operators[name](params)


registry = OperatorRegistry()


def _validate_operator_name(operator_name: str) -> None:
    """Validate the format of an operator registry name

    Business logic:
        1. Accept the operator registry name
        2. Check whether it matches snake_case rules
        3. Raise ValueError when it is invalid

    Args:
        operator_name (str): Registry name to validate.

    Returns:
        None: Returns nothing when validation passes.

    Examples:
        >>> _validate_operator_name("text_llm_synthesis")
    """
    if (
        not operator_name
        or not operator_name[0].isalpha()
        or not operator_name.islower()
        or any(not (char.islower() or char.isdigit() or char == "_") for char in operator_name)
    ):  # Workflow configuration allows only snake_case names.
        raise ValueError(f"operator_name must be snake_case: {operator_name}")


def register_operator(operator_cls: Type[BaseOperator]) -> Type[BaseOperator]:
    """Register an operator through decorator syntax

    Business logic:
        1. Accept an operator class
        2. Delegate registration to the global registry
        3. Return the original operator class

    Args:
        operator_cls (Type[BaseOperator]): Operator class to register.

    Returns:
        Type[BaseOperator]: Original operator class.

    Examples:
        >>> callable(register_operator)
        True
    """
    return registry.register(operator_cls)


def load_custom_operators(operator_refs: list[str] | None, base_dir: Path | None = None) -> None:
    """Load and register user-defined synthesis operators

    Business logic:
        1. Traverse file or module references from workflow custom_operators
        2. Import modules and scan for BaseOperator subclasses
        3. Register them in the global registry for workflow steps

    Args:
        operator_refs (list[str] | None): List of custom operator files or modules.
        base_dir (Path | None): Base directory for resolving relative paths.

    Returns:
        None: Mutates the global registry directly.

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
        if not operator_classes:  # Each module must provide at least one valid operator class.
            raise ValueError(f"No BaseOperator subclass found in custom operator: {operator_ref}")
        for operator_cls in operator_classes:  # Register every valid operator class in the module.
            if operator_cls.operator_name not in registry._operators:  # Avoid duplicate registration during repeated validate calls.
                registry.register(operator_cls)


def _load_operator_module(operator_ref: str, base_dir: Path | None = None) -> Any:
    """Import a user-defined synthesis-operator module

    Business logic:
        1. Determine whether the config value points to a Python file
        2. Load file paths through importlib.util
        3. Import non-file values as Python module names

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
    if not candidate.is_absolute():  # Resolve relative paths from the workflow directory.
        candidate = (base_dir or Path.cwd()) / candidate
    if operator_ref.endswith(".py") or candidate.exists():  # Import file references by filesystem path.
        if not candidate.exists():  # Fail when the declared file does not exist.
            raise FileNotFoundError(f"Custom operator file not found: {candidate}")
        module_name = f"synthesis_custom_operator_{abs(hash(str(candidate)))}"
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:  # Loading is impossible when the import spec is missing.
            raise ImportError(f"Cannot import custom operator file: {candidate}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(operator_ref)
