from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


class DataLeakageGuardOperator(BaseOperator):
    operator_name: str = "data_leakage_guard"  # Operator identifier used by workflow configs and the registry.

    DEFAULT_FORBIDDEN_KEYS: set[str] = {  # Leakage-prone keys that must not appear in input samples.
        "expected",
        "expected_action",
        "expected_clean",
        "expected_file",
        "expected_keywords",
        "ground_truth",
        "gold",
        "label_for_eval",
        "manifest",
        "oracle",
        "reference_image_path",
        "reference_path",
        "source_reference",
        "target_action",
    }

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        """Scan a sample for answer-like or reference-like leakage fields.

        Business logic:
            1. Read the configured forbidden-key set.
            2. Recursively scan the sample structure for forbidden field names.
            3. Record leakage metrics and issue tags when any hit is found.

        Args:
                item (dict[str, Any]): Current sample dictionary.

        Returns:
            dict[str, Any]: Updated sample dictionary.

        Examples:
            >>> process
            process
        """
        forbidden = set(self.config.get("forbidden_keys", [])) or self.DEFAULT_FORBIDDEN_KEYS
        hits: list[str] = []
        self._scan(item, forbidden, path="$", hits=hits)
        if hits:  # Record issues and evidence when forbidden keys are detected.
            self.add_issue(item, "data_leakage_suspected")
            self.set_metric(item, "data_leakage_guard_passed", False)
            self.set_metric(item, "data_leakage_hits", hits[:20])
        else:
            self.set_metric(item, "data_leakage_guard_passed", True)
        return item

    def _scan(self, value: Any, forbidden: set[str], path: str, hits: list[str]) -> None:
        """Recursively scan nested values for forbidden field names.

        Business logic:
            1. Descend through dictionaries and lists recursively.
            2. Record the access path for any forbidden key that appears.
            3. Accumulate hit paths in the provided output list.

        Args:
                value (Any): Current value being scanned.
                forbidden (set[str]): Set of forbidden field names.
                path (str): Current traversal path.
                hits (list[str]): Collected hit paths.

        Returns:
            None: The method mutates `hits` in place.

        Examples:
            >>> _scan
            _scan
        """
        if isinstance(value, dict):  # Recurse through mapping keys and values.
            for key, child in value.items():  # Visit each nested field.
                child_path = f"{path}.{key}"
                if str(key) in forbidden:  # Record any forbidden answer or reference field by path.
                    hits.append(child_path)
                self._scan(child, forbidden, child_path, hits)
        elif isinstance(value, list):
            for index, child in enumerate(value):  # Use list indexes in hit paths to keep leakage locations traceable.
                self._scan(child, forbidden, f"{path}[{index}]", hits)
