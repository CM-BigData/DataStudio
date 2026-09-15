import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from quality_eval.cli.main import build_parser
from quality_eval.runtime.executor import WorkflowExecutor
from quality_eval.runtime.input_adapter import InputAdapter, QualityItemNormalizer
from quality_eval.runtime.io import DataReader
from quality_eval.runtime.path_security import display_path, resolve_allowed_roots, safe_output_path, safe_path, validate_task_id
from quality_eval.runtime.registry import load_custom_operators
from quality_eval.runtime.report import regenerate_markdown_report


def test_quality_media_id_uses_pure_path_without_filesystem_resolution() -> None:
    item = QualityItemNormalizer({"task_type": "image"}).normalize(
        {"payload": {"image_path": "../external/private/sample.jpg"}},
        source={"format": "stdin"},
    )

    assert item["id"] == "sample"
    assert item["payload"]["image_path"] == "../external/private/sample.jpg"


def test_quality_safe_path_rejects_control_characters() -> None:
    with pytest.raises(ValueError, match="control characters"):
        safe_path("bad\x00path.yaml", name="workflow config")


def test_quality_parser_converts_cli_paths_to_path_objects() -> None:
    args = build_parser().parse_args(
        ["run", "--config", "workflows/text_dataset_eval.yaml", "--allow-root", "data"]
    )

    assert args.config == Path("workflows/text_dataset_eval.yaml")
    assert args.allow_root == [Path("data")]


def test_quality_safe_path_enforces_authorized_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "授权 root"
    allowed_root.mkdir()
    roots = resolve_allowed_roots([allowed_root])

    accepted = safe_path(
        "中文 data/workflow.yaml",
        name="workflow config",
        base_dir=allowed_root,
        allowed_roots=roots,
    )
    assert accepted == (allowed_root / "中文 data" / "workflow.yaml").resolve()

    with pytest.raises(ValueError, match="authorized root"):
        safe_path(
            tmp_path.parent / "outside.yaml",
            name="workflow config",
            allowed_roots=(allowed_root.resolve(),),
        )


def test_quality_safe_path_rejects_symlink_escape(tmp_path: Path) -> None:
    allowed_root = tmp_path / "root"
    outside = tmp_path / "outside"
    allowed_root.mkdir()
    outside.mkdir()
    link = allowed_root / "external-link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")

    with pytest.raises(ValueError, match="authorized root"):
        safe_path(link / "report.md", allowed_roots=(allowed_root.resolve(),))


def test_quality_directory_reader_rejects_discovered_file_outside_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / "secret.txt"
    outside_file.write_text("outside secret", encoding="utf-8")

    def resolver(value: str | Path) -> Path:
        return safe_path(value, allowed_roots=(allowed_root.resolve(),))

    adapter = InputAdapter({}, {"type": "directory", "path": str(allowed_root)}, resolver)

    with patch.object(Path, "rglob", return_value=iter([outside_file])):
        with pytest.raises(ValueError, match="authorized root"):
            adapter.read()


def test_quality_directory_reader_accepts_discovered_file_inside_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    input_file = allowed_root / "sample.txt"
    input_file.write_text("allowed text", encoding="utf-8")

    def resolver(value: str | Path) -> Path:
        return safe_path(value, allowed_roots=(allowed_root.resolve(),))

    adapter = InputAdapter({}, {"type": "directory", "path": str(allowed_root)}, resolver)

    rows = adapter.read()

    assert [row["payload"]["text"] for row in rows] == ["allowed text"]


@pytest.mark.parametrize("field,task_type", [("image_path", "image"), ("audio_path", "audio")])
def test_quality_record_file_paths_cannot_escape_authorized_root(
    tmp_path: Path,
    field: str,
    task_type: str,
) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / "private.bin"
    outside_file.write_bytes(b"private")
    manifest = allowed_root / "input.jsonl"
    manifest.write_text(json.dumps({"id": "sample", "payload": {field: str(outside_file)}}) + "\n", encoding="utf-8")

    def resolver(value: str | Path) -> Path:
        return safe_path(value, base_dir=allowed_root, allowed_roots=(allowed_root.resolve(),))

    adapter = InputAdapter(
        {"task_type": task_type},
        {"type": "jsonl", "path": str(manifest)},
        resolver,
    )

    with pytest.raises(ValueError, match="authorized root"):
        adapter.read()


def test_quality_image_folder_annotation_cannot_escape_authorized_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    image_root = allowed_root / "images"
    outside_root = tmp_path / "outside"
    image_root.mkdir(parents=True)
    outside_root.mkdir()
    annotation_path = image_root / "annotations.json"
    annotation_path.write_text(
        json.dumps([{"id": "sample", "image_path": str(outside_root / "private.jpg")}]),
        encoding="utf-8",
    )

    def resolver(value: str | Path) -> Path:
        return safe_path(value, base_dir=allowed_root, allowed_roots=(allowed_root.resolve(),))

    with pytest.raises(ValueError, match="authorized root"):
        DataReader(resolver).read(
            {"task_type": "image"},
            {"type": "image_folder", "path": str(image_root), "annotation_path": str(annotation_path)},
        )


def test_quality_custom_operator_file_must_stay_under_authorized_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    plugin = outside_root / "outside_operator.py"
    plugin.write_text("raise RuntimeError('must not execute')", encoding="utf-8")

    with pytest.raises(ValueError, match="authorized root"):
        load_custom_operators(
            [str(plugin)],
            base_dir=allowed_root,
            allowed_roots=(allowed_root.resolve(),),
        )


def test_quality_safe_output_path_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file path"):
        safe_output_path(tmp_path, allowed_roots=(tmp_path.resolve(),))


def test_quality_task_id_accepts_safe_unicode_identifier() -> None:
    assert validate_task_id("任务_2026-07.30") == "任务_2026-07.30"


@pytest.mark.parametrize(
    "task_id",
    ["..", "../escaped", "..\\escaped", "C:escaped", "bad task", "task.", "CON", "NUL", "AUX", "COM1", "LPT1"],
)
def test_quality_task_id_rejects_path_components(task_id: str) -> None:
    with pytest.raises(ValueError, match="task id"):
        validate_task_id(task_id)


def test_quality_executor_rejects_task_id_path_escape(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    config = {
        "workflow": {"id": "path_probe"},
        "input": {"type": "raw_text", "text": "probe"},
        "output": {
            "result_path": "result.jsonl",
            "summary_path": "summary.json",
            "report_path": "report.md",
        },
        "steps": [],
    }

    with pytest.raises(ValueError, match="task id"):
        WorkflowExecutor(
            config,
            allowed_root / "workflow.yaml",
            task_id="..\\..\\escaped",
            allowed_roots=(allowed_root.resolve(),),
        )

    assert not (tmp_path / "escaped.json").exists()


def _create_directory_link(link: Path, target: Path) -> None:
    """Create a directory link without requiring Windows symlink privileges."""
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip(f"directory junctions are unavailable: {result.stderr or result.stdout}")
        return
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks are unavailable: {exc}")


@pytest.mark.parametrize("derived_directory", ["checkpoints", "logs", "errors"])
def test_quality_executor_rejects_derived_directory_link_escape(
    tmp_path: Path,
    derived_directory: str,
) -> None:
    """Verify derived runtime directories cannot redirect outside authorized roots."""
    allowed_root = tmp_path / "allowed"
    output_dir = allowed_root / "output"
    outside_root = tmp_path / "outside"
    output_dir.mkdir(parents=True)
    outside_root.mkdir()
    _create_directory_link(output_dir / derived_directory, outside_root)
    config = {
        "workflow": {"id": "derived_path_probe"},
        "input": {"type": "raw_text", "text": "probe"},
        "output": {
            "result_path": "result.jsonl",
            "summary_path": "summary.json",
            "report_path": "report.md",
        },
        "steps": [],
    }

    with pytest.raises(ValueError, match="authorized root"):
        WorkflowExecutor(
            config,
            allowed_root / "workflow.yaml",
            task_id="derived_path_probe",
            output_dir=output_dir,
            allowed_roots=(allowed_root.resolve(),),
        )

    assert list(outside_root.iterdir()) == []


def test_quality_executor_rejects_output_directory_outside_authorized_roots(tmp_path: Path) -> None:
    """Verify programmatic output-directory overrides retain the authorized-root boundary."""
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    config = {
        "workflow": {"id": "output_override_probe"},
        "input": {"type": "raw_text", "text": "probe"},
        "output": {
            "result_path": "result.jsonl",
            "summary_path": "summary.json",
            "report_path": "report.md",
        },
        "steps": [],
    }

    with pytest.raises(ValueError, match="authorized root"):
        WorkflowExecutor(
            config,
            allowed_root / "workflow.yaml",
            task_id="output_override_probe",
            output_dir=outside_root,
            allowed_roots=(allowed_root.resolve(),),
        )

    assert list(outside_root.iterdir()) == []


def test_quality_display_path_hides_external_absolute_directory(tmp_path: Path) -> None:
    external = tmp_path / "private" / "report.md"

    assert display_path(external) == "report.md"


def test_export_report_rejects_summary_report_path_outside_summary_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    other_dir = tmp_path / "other"
    run_dir.mkdir()
    other_dir.mkdir()
    summary_path = run_dir / "summary.json"
    summary = {
        "task_id": "task",
        "workflow_id": "workflow",
        "modality": "text",
        "total_count": 0,
        "valid_count": 0,
        "abnormal_count": 0,
        "base_quality_score": 0,
        "annotation_quality_score": 0,
        "comprehensive_score": 0,
        "dimension_scores": {},
        "level_distribution": {},
        "issue_distribution": {},
        "duplicate_sample_ids": [],
        "low_quality_samples": [],
        "high_risk_samples": [],
        "annotation_problem_samples": [],
        "enhanced_metric_status": {},
        "gb_mapping": [],
        "rectification_suggestions": [],
        "paths": {"report_path": str(other_dir / "report.md")},
    }
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(ValueError, match="summary report path"):
        regenerate_markdown_report(summary_path)
