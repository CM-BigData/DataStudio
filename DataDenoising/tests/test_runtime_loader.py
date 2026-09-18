import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from denoise_workflow_engine.cli.main import build_parser
from denoise_workflow_engine.operators.image_denoising.repair import ImageRepairOperator
from denoise_workflow_engine.utilities.video.base import VideoOperator
from denoise_workflow_engine.runtime.executor import WorkflowExecutor
from denoise_workflow_engine.runtime.input_adapter import InputAdapter
from denoise_workflow_engine.runtime.loader import resolve_allowed_roots, resolve_path
from denoise_workflow_engine.runtime.registry import build_default_registry


def test_denoise_resolve_path_normalizes_relative_path(tmp_path: Path) -> None:
    resolved = resolve_path("outputs/run", tmp_path)

    assert resolved == (tmp_path / "outputs" / "run").resolve()


def test_denoise_resolve_path_rejects_control_characters() -> None:
    with pytest.raises(ValueError, match="control characters"):
        resolve_path("bad\x00path")


def test_denoise_parser_converts_cli_paths_to_path_objects() -> None:
    args = build_parser().parse_args(
        ["run", "--config", "workflows/denoise_auto.yaml", "--allow-root", "data"]
    )

    assert args.config == Path("workflows/denoise_auto.yaml")
    assert args.allow_root == [Path("data")]


def test_denoise_resolve_path_enforces_authorized_roots(tmp_path: Path) -> None:
    allowed_root = tmp_path / "授权 root"
    allowed_root.mkdir()
    roots = resolve_allowed_roots([allowed_root])

    accepted = resolve_path(
        "中文 data/output.jsonl",
        allowed_root,
        allowed_roots=roots,
        name="run directory",
    )
    assert accepted == (allowed_root / "中文 data" / "output.jsonl").resolve()

    with pytest.raises(ValueError, match="authorized root"):
        resolve_path(
            tmp_path.parent / "outside.jsonl",
            allowed_root,
            allowed_roots=(allowed_root.resolve(),),
            name="run directory",
        )


def test_denoise_resolve_path_rejects_symlink_escape(tmp_path: Path) -> None:
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
        resolve_path(link / "result.jsonl", allowed_roots=(allowed_root.resolve(),))


def test_denoise_directory_reader_rejects_discovered_file_outside_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / "secret.txt"
    outside_file.write_text("outside secret", encoding="utf-8")
    adapter = InputAdapter(
        {"type": "directory", "path": str(allowed_root)},
        allowed_root,
        allowed_roots=(allowed_root.resolve(),),
    )

    with patch.object(Path, "rglob", return_value=iter([outside_file])):
        with pytest.raises(ValueError, match="authorized root"):
            list(adapter.read())


def test_denoise_directory_reader_accepts_discovered_file_inside_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    input_file = allowed_root / "sample.txt"
    input_file.write_text("allowed text", encoding="utf-8")
    adapter = InputAdapter(
        {"type": "directory", "path": str(allowed_root)},
        allowed_root,
        allowed_roots=(allowed_root.resolve(),),
    )

    rows = list(adapter.read())

    assert [row["payload"]["text"] for row in rows] == ["allowed text"]


@pytest.mark.parametrize("field", ["image_path", "video_path", "reference_image_path", "text_file"])
def test_denoise_record_file_paths_cannot_escape_authorized_root(tmp_path: Path, field: str) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    outside_file = outside_root / "private.bin"
    outside_file.write_bytes(b"private")
    manifest = allowed_root / "input.jsonl"
    manifest.write_text(json.dumps({"id": "sample", "payload": {field: str(outside_file)}}) + "\n", encoding="utf-8")

    adapter = InputAdapter(
        {"type": "jsonl", "path": str(manifest)},
        allowed_root,
        allowed_roots=(allowed_root.resolve(),),
    )

    with pytest.raises(ValueError, match="authorized root"):
        list(adapter.read())


def test_denoise_image_repair_rejects_sample_id_path_escape(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    run_dir = allowed_root / "run"
    run_dir.mkdir(parents=True)
    source = allowed_root / "source.jpg"
    Image.new("RGB", (8, 8), "white").save(source)
    item = {
        "id": "../../escaped",
        "modality": "image",
        "payload": {"image_path": str(source)},
        "issues": ["blur"],
        "metrics": {},
    }
    operator = ImageRepairOperator(
        {
            "_runtime": {
                "base_dir": str(allowed_root),
                "run_dir": str(run_dir),
                "allowed_roots": [str(allowed_root.resolve())],
            }
        }
    )

    result = operator.process(item)

    assert "image_repair_failed" in result["issues"]
    assert not (allowed_root / "escaped_repaired.jpg").exists()
    assert not (tmp_path / "escaped_repaired.jpg").exists()


def test_denoise_video_artifact_dir_rejects_sample_id_path_escape(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    run_dir = allowed_root / "run"
    run_dir.mkdir(parents=True)
    operator = VideoOperator(
        {
            "_runtime": {
                "base_dir": str(allowed_root),
                "run_dir": str(run_dir),
                "allowed_roots": [str(allowed_root.resolve())],
            }
        }
    )

    with pytest.raises(ValueError, match="sample id"):
        operator.run_dir({"id": "../../escaped", "intermediate": {}}, "frames")
    assert not (allowed_root / "escaped").exists()


def test_denoise_custom_operator_file_must_stay_under_authorized_root(tmp_path: Path) -> None:
    allowed_root = tmp_path / "allowed"
    outside_root = tmp_path / "outside"
    allowed_root.mkdir()
    outside_root.mkdir()
    plugin = outside_root / "outside_operator.py"
    plugin.write_text("raise RuntimeError('must not execute')", encoding="utf-8")

    with pytest.raises(ValueError, match="authorized root"):
        build_default_registry(
            custom_operators=[str(plugin)],
            base_dir=allowed_root,
            allowed_roots=(allowed_root.resolve(),),
        )


@pytest.mark.parametrize("output_key", ["clean_path", "dropped_path", "review_path", "report_path"])
def test_denoise_executor_rejects_output_escape_from_run_dir(tmp_path: Path, output_key: str) -> None:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    output = {
        "run_dir": "run",
        "clean_path": "clean.jsonl",
        "dropped_path": "dropped.jsonl",
        "review_path": "review.jsonl",
        "report_path": "report.md",
    }
    output[output_key] = "../../escaped.jsonl"
    config = {
        "workflow": {"id": "path_probe", "checkpoint": False},
        "input": {"type": "raw_text", "text": "probe"},
        "output": output,
        "steps": [],
    }

    with pytest.raises(ValueError, match="authorized root"):
        WorkflowExecutor(
            config,
            build_default_registry(),
            base_dir=allowed_root,
            allowed_roots=(allowed_root.resolve(),),
        ).run()

    assert not (tmp_path / "escaped.jsonl").exists()


def test_denoise_executor_validates_fixed_run_files(tmp_path: Path) -> None:
    """Verify every fixed runtime file passes through canonical path validation."""
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    config = {
        "workflow": {"id": "fixed_path_probe", "checkpoint": True},
        "input": {"type": "raw_text", "text": "probe"},
        "output": {"run_dir": "run"},
        "steps": [],
    }

    with patch("denoise_workflow_engine.runtime.executor.resolve_path", wraps=resolve_path) as resolver:
        WorkflowExecutor(
            config,
            build_default_registry(),
            base_dir=allowed_root,
            allowed_roots=(allowed_root.resolve(),),
        ).run()

    validated_names = {call.kwargs.get("name") for call in resolver.call_args_list}
    assert {"checkpoint path", "operator log path", "metrics path"} <= validated_names


@pytest.mark.parametrize("file_name", ["checkpoint.json", "operator_logs.jsonl", "metrics.json"])
def test_denoise_executor_rejects_fixed_file_symlink_escape(tmp_path: Path, file_name: str) -> None:
    """Verify fixed runtime files cannot follow links outside the run directory."""
    allowed_root = tmp_path / "allowed"
    run_dir = allowed_root / "run"
    outside_root = tmp_path / "outside"
    run_dir.mkdir(parents=True)
    outside_root.mkdir()
    outside_file = outside_root / file_name
    outside_file.write_text("outside", encoding="utf-8")
    try:
        os.symlink(outside_file, run_dir / file_name)
    except OSError as exc:
        pytest.skip(f"file symlinks are unavailable: {exc}")

    config = {
        "workflow": {"id": "fixed_link_probe", "checkpoint": True},
        "input": {"type": "raw_text", "text": "probe"},
        "output": {"run_dir": str(run_dir)},
        "steps": [],
    }

    with pytest.raises(ValueError, match="authorized root"):
        WorkflowExecutor(
            config,
            build_default_registry(),
            base_dir=allowed_root,
            allowed_roots=(allowed_root.resolve(),),
        ).run()

    assert outside_file.read_text(encoding="utf-8") == "outside"
