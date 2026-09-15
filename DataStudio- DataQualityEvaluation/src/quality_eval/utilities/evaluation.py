from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator


StageSpec = tuple[str, type[BaseOperator]]
StageDependencies = dict[str, tuple[str, ...]]


def setup_stages(
    items: list[dict[str, Any]],
    context: dict[str, Any],
    config: dict[str, Any],
    specs: list[StageSpec],
    enabled: set[str],
) -> list[BaseOperator]:
    """Instantiate and setup selected internal stages.

    Business logic:
        1. Instantiate only the already-resolved stage names.
        2. Preserve the stage order declared by the caller.
        3. Run every selected stage setup hook.

    Args:
        items (list[dict[str, Any]]): All workflow samples.
        context (dict[str, Any]): Shared workflow context.
        config (dict[str, Any]): End-to-end operator config used to instantiate each selected stage.
        specs (list[StageSpec]): Candidate stage specs.
        enabled (set[str]): Selected stage names resolved by the modality-specific pipeline.

    Returns:
        list[BaseOperator]: Prepared internal stages.

    Examples:
        >>> setup_stages([], {}, {}, [], set())
        []
    """
    selected = [stage_cls(config) for check_name, stage_cls in specs if check_name in enabled]

    for stage in selected:  # Run setup hooks after stage instantiation so dataset-level state is ready before processing.
        stage.setup(items, context)

    return selected


def process_stages(item: dict[str, Any], stages: list[BaseOperator]) -> dict[str, Any]:
    """Run selected internal stages in order.

    Business logic:
        1. Ensure the sample has required mutable containers.
        2. Execute each internal stage sequentially.
        3. Return the updated sample.

    Args:
        item (dict[str, Any]): Current sample.
        stages (list[BaseOperator]): Prepared internal stages.

    Returns:
        dict[str, Any]: Updated sample.

    Examples:
        >>> process_stages({"issues": []}, [])["issues"]
        []
    """
    item.setdefault("issues", [])
    item.setdefault("metrics", {})
    item.setdefault("intermediate", {})

    for stage in stages:  # Replay the prepared internal stages in declaration order for deterministic sample mutation.
        item = stage.process(item)

    return item


def enabled_checks(config: dict[str, Any], specs: list[StageSpec], dependencies: StageDependencies) -> set[str]:
    """Resolve enabled check names.

    Business logic:
        1. Read `enabled_checks` from top-level config, step config, or step params.
        2. Include all stages when no explicit list is configured.
        3. Add prerequisites for explicitly enabled internal checks.
        4. Always include `score` unless the caller explicitly provides a list without it.

    Args:
        config (dict[str, Any]): End-to-end operator config.
        specs (list[StageSpec]): Candidate stage specs.
        dependencies (StageDependencies): Required prerequisite stages keyed by public check name.

    Returns:
        set[str]: Enabled check names.

    Examples:
        >>> enabled_checks({"enabled_checks": ["length"]}, [("length", BaseOperator), ("score", BaseOperator)], {})
        {'length', 'score'}
    """
    all_names = {name for name, _ in specs}
    enabled_checks = config.get("enabled_checks")

    if enabled_checks is None:  # Support direct top-level configuration for simple workflow definitions.
        enabled_checks = config.get("step", {}).get("enabled_checks")

    if enabled_checks is None:  # Support nested step-level configuration after workflow loader normalization.
        enabled_checks = config.get("step", {}).get("params", {}).get("enabled_checks")

    if enabled_checks is None:  # When no explicit subset is configured, keep every declared stage enabled.
        return all_names

    enabled = {str(name) for name in enabled_checks}

    for check_name in list(enabled):  # Expand user-facing checks into the prerequisite internal stages they require.
        enabled.update(dependencies.get(check_name, ()))

    enabled.add("score")

    return enabled & all_names
