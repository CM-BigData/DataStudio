from __future__ import annotations

from parse_engine.models import DataItem


def run_stages(item: DataItem, stages: list[object]) -> DataItem:
    """Run internal operator package stages for one sample."""
    for stage in stages:
        stage.setup()
    try:
        result = item
        for stage in stages:
            if result.action == "failed":
                break
            result = stage.process(result)
        return result
    finally:
        for stage in stages:
            stage.teardown()


def stage_config(config: dict, name: str, defaults: dict | None = None) -> dict:
    """Build a config dictionary for an internal operator package stage."""
    merged = dict(defaults or {})
    nested = config.get(name, {})
    if isinstance(nested, dict):
        merged.update(nested)
    return merged
