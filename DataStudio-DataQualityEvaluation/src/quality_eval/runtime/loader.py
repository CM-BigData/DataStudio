from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .path_security import safe_path
from .schema import SchemaValidator


class WorkflowLoader:
    def load(self, path: str | Path) -> dict[str, Any]:
        """Load and validate a workflow configuration file.

        Business logic:
            1. Convert the input path to a Path object.
            2. Select the YAML or JSON parser based on the file extension.
            3. Raise an error directly for unsupported extensions.
            4. Use SchemaValidator to validate the basic structure.

        Args:
            path (str | Path): Path to the workflow YAML or JSON config file.

        Returns:
            dict[str, Any]: Configuration dictionary that passed basic structure validation.

        Examples:
            >>> isinstance(WorkflowLoader(), WorkflowLoader)
            True
        """
        config_path = safe_path(path, name="workflow config")
        if config_path.suffix.lower() not in {".yaml", ".yml", ".json"}:
            raise ValueError(f"Unsupported workflow config type: {config_path.suffix}")
        if not config_path.is_file():
            raise FileNotFoundError(f"Workflow config not found: {config_path.name}")
        with config_path.open("r", encoding="utf-8") as handle:
            if config_path.suffix.lower() in {".yaml", ".yml"}:  # YAML is the primary workflow config format in this project.
                config = yaml.safe_load(handle)
            elif config_path.suffix.lower() == ".json":
                config = json.load(handle)

        SchemaValidator().validate_config(config)
        return config
