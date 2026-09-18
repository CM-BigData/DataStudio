from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Any, Sequence, Type

from quality_eval.operators.common.base import BaseOperator
from quality_eval.runtime.path_security import safe_path


class OperatorRegistry:
    def __init__(self) -> None:
        """Initialize the operator registry.

        Business logic:
            1. Create the mapping from operator names to operator classes.
            2. Support registration only through the single `operator_name` entry.
            3. Let workflow configs resolve operator classes by name.

        Args:
            None.

        Returns:
            None: The initializer does not return a business value.

        Examples:
            >>> OperatorRegistry().names()
            []
        """
        self._operators: dict[str, Type[BaseOperator]] = {}  # Operator mapping table that stores name-to-class registrations.

    def register(self, operator_cls: Type[BaseOperator]) -> Type[BaseOperator]:
        """Register an operator class.

        Business logic:
            1. Validate the operator class `operator_name`.
            2. Register the stable name from the class attribute `operator_name`.
            3. Return the original class to support decorator usage.

        Args:
            operator_cls (Type[BaseOperator]): Operator class to register.

        Returns:
            Type[BaseOperator]: Original operator class.

        Examples:
            >>> registry = OperatorRegistry()
            >>> callable(registry.register)
            True
        """
        if not inspect.isclass(operator_cls) or not issubclass(operator_cls, BaseOperator):  # Register only BaseOperator subclasses.
            raise ValueError(f"Operator must inherit BaseOperator: {operator_cls}")
        _validate_operator_name(operator_cls.operator_name)
        if operator_cls.operator_name in self._operators:  # Duplicate names would make config resolution ambiguous.
            raise ValueError(f"Duplicate operator name: {operator_cls.operator_name}")
        self._operators[operator_cls.operator_name] = operator_cls
        return operator_cls

    def get(self, name: str) -> Type[BaseOperator]:
        """Get an operator class by name.

        Business logic:
            1. Look up the operator name in the registry mapping.
            2. Raise KeyError for unregistered names to expose config errors.
            3. Return the operator class for executor instantiation when present.

        Args:
            name (str): Stable registered name.

        Returns:
            Type[BaseOperator]: Registered operator class.

        Examples:
            >>> registry = OperatorRegistry()
            >>> isinstance("text_length_eval", str)
            True
        """
        if name not in self._operators:  # Fail immediately when the workflow references an unknown operator.
            raise KeyError(f"Operator is not registered: {name}")
        return self._operators[name]

    def names(self) -> list[str]:
        """List registered operator names.

        Business logic:
            1. Read all names from the registry mapping.
            2. Sort them to keep command-line output stable.
            3. Return the list for `list-operators`.

        Args:
            None.

        Returns:
            list[str]: List of registered operator names.

        Examples:
            >>> OperatorRegistry().names()
            []
        """
        return sorted(self._operators)


registry = OperatorRegistry()


def load_custom_operators(
    operator_refs: list[str] | None,
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> None:
    """Load and register user-defined quality-evaluation operators.

    Business logic:
        1. Iterate through file or module references in workflow `custom_operators`.
        2. Import each module and scan for operator classes that inherit from BaseOperator.
        3. Register them in the global registry so workflow steps can reference them.

    Args:
        operator_refs (list[str] | None): List of user-defined operator files or modules.
        base_dir (Path | None): Base path used for resolving relative paths.

    Returns:
        None: Modifies the global registry directly.

    Examples:
        >>> load_custom_operators([])
    """
    for operator_ref in operator_refs or []:  # Load each file or module one by one.
        module = _load_operator_module(operator_ref, base_dir, allowed_roots=allowed_roots)
        operator_classes = [
            cls
            for _, cls in inspect.getmembers(module, inspect.isclass)
            if cls is not BaseOperator and issubclass(cls, BaseOperator) and cls.__module__ == module.__name__
        ]
        if not operator_classes:  # Each module must provide at least one valid operator class.
            raise ValueError(f"No BaseOperator subclass found in custom operator: {operator_ref}")
        for operator_cls in operator_classes:  # Register every valid operator class in the module.
            if operator_cls.operator_name not in registry._operators:  # Avoid duplicate registration across validate and run commands.
                registry.register(operator_cls)


def _load_operator_module(
    operator_ref: str,
    base_dir: Path | None = None,
    allowed_roots: Sequence[Path] | None = None,
) -> Any:
    """Import a user-defined quality-evaluation operator module.

    Business logic:
        1. Determine whether the config value points to a Python file.
        2. Load file paths through `importlib.util`.
        3. Import non-file paths by Python module name.

    Args:
        operator_ref (str): Python file path or module path.
        base_dir (Path | None): Base path used for resolving relative paths.

    Returns:
        Any: Imported module object.

    Examples:
        >>> callable(_load_operator_module)
        True
    """
    candidate = Path(operator_ref)
    if not candidate.is_absolute():  # Resolve relative paths from the workflow directory.
        candidate = (base_dir or Path.cwd()) / candidate
    if operator_ref.endswith(".py") or candidate.exists():  # Import by file path.
        candidate = safe_path(
            candidate,
            name="custom operator file",
            allowed_roots=allowed_roots,
        )
        if not candidate.exists():  # Fail when the declared file does not exist.
            raise FileNotFoundError(f"Custom operator file not found: {candidate}")
        module_name = f"quality_eval_custom_operator_{abs(hash(str(candidate)))}"
        spec = importlib.util.spec_from_file_location(module_name, candidate)
        if spec is None or spec.loader is None:  # The module cannot be loaded when the spec or loader is missing.
            raise ImportError(f"Cannot import custom operator file: {candidate}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    return importlib.import_module(operator_ref)


def _validate_operator_name(operator_name: str) -> None:
    """Validate the operator registration-name format.

    Business logic:
        1. Receive the operator registration name.
        2. Check whether it follows the `snake_case` character rules.
        3. Raise ValueError when the name is invalid.

    Args:
        operator_name (str): Registration name to validate.

    Returns:
        None: No business value is returned when validation succeeds.

    Examples:
        >>> _validate_operator_name("text_length_eval")
    """
    if (
        not operator_name
        or not operator_name[0].isalpha()
        or not operator_name.islower()
        or any(not (char.islower() or char.isdigit() or char == "_") for char in operator_name)
    ):  # Workflow configs allow only snake_case names.
        raise ValueError(f"operator_name must be snake_case: {operator_name}")
