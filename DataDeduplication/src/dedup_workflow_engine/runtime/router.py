from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from dedup_workflow_engine.runtime.loader import load_workflow_config


SUPPORTED_MODALITIES = ("text", "image", "audio")  # Workflow config: built-in data modalities supported by auto-routing.
STRICT_WORKFLOWS = dict(text="text_dedup_strict.yaml", image="image_dedup_strict.yaml", audio="audio_dedup_strict.yaml")  # Workflow config: workflow template filename for each modality in the strict profile.
BASIC_WORKFLOWS = dict(text="text_dedup.yaml", image="image_dedup.yaml", audio="audio_dedup.yaml")  # Workflow config: workflow template filename for each modality in the basic profile.


def load_and_route_input(input_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Read mixed JSONL input and route samples by modality.

    Business logic:
        1. Block ground-truth files from being used as workflow input.
        2. Parse the JSONL file line by line and detect each sample's modality.
        3. Return the non-empty text, image, and audio buckets.

    Args:
        input_path (Path): JSONL file containing one or more sample modalities.

    Returns:
        dict[str, list[dict[str, Any]]]: Samples grouped by modality.

    Raises:
        ValueError: Raised when the input points to ground truth or contains unroutable samples.

    Examples:
        >>> load_and_route_input(Path("mixed.jsonl"))  # doctest: +SKIP
        {'text': [{'id': 't1'}]}
    """
    if "ground_truth" in str(input_path).lower():  # Prevent evaluation labels from leaking into workflow inputs.
        raise ValueError(f"workflow input must not point to ground truth: {input_path}")
    routed: dict[str, list[dict[str, Any]]] = {modality: [] for modality in SUPPORTED_MODALITIES}
    with input_path.open("r", encoding="utf-8-sig") as handle:
        for line_no, line in enumerate(handle, start=1):  # Preserve line numbers for actionable routing errors.
            if not line.strip():  # Blank lines are ignored to tolerate hand-edited JSONL files.
                continue
            item = json.loads(line)
            modality = detect_modality(item)
            if modality not in routed:  # Ambiguous or unknown records cannot be routed safely.
                raise ValueError(f"unsupported or unknown modality at {input_path}:{line_no}")
            routed[modality].append(item)
    return {modality: items for modality, items in routed.items() if items}


def detect_modality(item: dict[str, Any]) -> str | None:
    """Detect a sample's modality from explicit fields or payload structure.

    Business logic:
        1. Prefer a valid modality from item.modality.
        2. If no explicit modality exists, inspect payload.text, payload.image_path, and payload.audio_path.
        3. Return a result only when exactly one modality can be identified.

    Args:
        item (dict[str, Any]): A single input sample record.

    Returns:
        str | None: The detected modality, or None when the sample is ambiguous or unsupported.

    Examples:
        >>> detect_modality({"payload": {"text": "hello"}})
        'text'
    """
    modality = str(item.get("modality", "")).strip().lower()
    if modality in SUPPORTED_MODALITIES:  # Explicit valid modality always wins over payload inference.
        return modality

    payload = item.get("payload", {})
    if not isinstance(payload, dict):  # Non-mapping payloads cannot expose modality-specific fields.
        return None
    detected = []
    if "text" in payload:  # Text workflows consume payload.text.
        detected.append("text")
    if "image_path" in payload:  # Image workflows consume payload.image_path.
        detected.append("image")
    if "audio_path" in payload:  # Audio workflows consume payload.audio_path.
        detected.append("audio")
    if len(detected) == 1:  # Exactly one modality-specific field is safe to infer.
        return detected[0]
    if len(detected) > 1:  # Mixed modality hints must be resolved by explicit modality.
        return None
    return None


def workflow_path_for_modality(workflow_dir: Path, modality: str, profile: str) -> Path:
    """Resolve the workflow template path for a modality and profile.

    Business logic:
        1. Use the strict template mapping for the strict profile.
        2. Use the basic template mapping for all other profiles.
        3. Join the selected template filename under workflow_dir.

    Args:
        workflow_dir (Path): Directory containing workflow templates.
        modality (str): Routed sample modality.
        profile (str): Workflow profile name.

    Returns:
        Path: Workflow template path for the modality and profile.

    Raises:
        ValueError: Raised when no template is registered for the modality.

    Examples:
        >>> workflow_path_for_modality(Path("workflows"), "text", "strict")
        PosixPath('workflows/text_dedup_strict.yaml')
    """
    mapping = STRICT_WORKFLOWS if profile == "strict" else BASIC_WORKFLOWS
    try:
        return workflow_dir / mapping[modality]
    except KeyError as exc:
        raise ValueError(f"unsupported modality: {modality}") from exc


def build_routed_workflow_config(template_path: Path, input_path: Path, run_dir: Path) -> dict[str, Any]:
    """Build a routed workflow config from a template.

    Business logic:
        1. Deep-copy the template config so the source object is not modified.
        2. Inject the input path for the current modality bucket.
        3. Inject the output run_dir for the current modality bucket.

    Args:
        template_path (Path): Selected workflow template file.
        input_path (Path): Input JSONL path for the current modality bucket.
        run_dir (Path): Output directory for the current modality run.

    Returns:
        dict[str, Any]: Workflow config with injected input and output settings.

    Examples:
        >>> build_routed_workflow_config(Path("workflow.yaml"), Path("input.jsonl"), Path("run"))  # doctest: +SKIP
        {'input': {'path': 'input.jsonl'}}
    """
    config = copy.deepcopy(load_workflow_config(template_path))
    config.setdefault("input", {})["path"] = str(input_path)
    output = config.setdefault("output", {})
    output["run_dir"] = str(run_dir)
    return config


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a routed JSONL input file.

    Business logic:
        1. Create the parent directory for the target file.
        2. Serialize each sample as one JSON line.
        3. Use ensure_ascii=False to preserve original characters such as Chinese text.

    Args:
        path (Path): Output JSONL file path.
        rows (list[dict[str, Any]]): Sample records in a single modality bucket.

    Returns:
        None: The JSONL content is written to disk and nothing is returned.

    Examples:
        >>> write_jsonl(Path("out.jsonl"), [{"id": "1"}])  # doctest: +SKIP
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:  # Emit one JSON object per line for workflow input compatibility.
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
