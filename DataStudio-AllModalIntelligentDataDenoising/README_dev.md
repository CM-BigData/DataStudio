# DataStudio-AllModalIntelligentDataDenoising

> 中文版本: [README_dev_zh.md](README_dev_zh.md)
>
> Deployment and Usage Guide: [README.md](README.md)

DataStudio-AllModalIntelligentDataDenoising is a lightweight workflow engine for multimodal data cleaning and quality routing. It provides the `denoise` command-line entry point, reads text, image, image-text pair, and video samples from configurable inputs, runs built-in or custom denoising operators, and routes samples into keep, drop, and manual-review outputs.

The project package name is `denoise-workflow-engine`, the Python package path is `denoise_workflow_engine`, and the default production workflow is `workflows/denoise_auto.yaml`.

## Development Guide

### Developing Custom Operators

#### Platform User and Operator Developer Responsibilities

Platform users only need to prepare input, select a workflow, and run `validate -> run -> report`:

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
uv run denoise run -c workflows/denoise_auto.yaml
uv run denoise report -t outputs/latest
```

Operator developers package a complete dataset-processing capability as a `BaseOperator` subclass, declare a unique end-to-end `operator_name`, deliver it through `custom_operators`, and run it as the single workflow step. The platform still runs through the same `validate -> run -> report` commands and does not require command-line code changes.

#### Generate a Template

Start from the real command-line template and then fill business logic inside the generated `process` method:

```bash
mkdir -p workflows/plugins
uv run denoise operator-template --type text_denoise --name my_text_denoise --output workflows/plugins/my_text_denoise.py
uv run denoise operator-template --type image_denoise --name my_image_denoise --output workflows/plugins/my_image_denoise.py
uv run denoise operator-template --type video_denoise --name my_video_denoise --output workflows/plugins/my_video_denoise.py
uv run denoise operator-template --type image_text_pair_denoise --name my_pair_denoise --output workflows/plugins/my_pair_denoise.py
uv run denoise operator-template --type auto_denoise --name my_auto_denoise --output workflows/plugins/my_auto_denoise.py
```

Allowed `--type` values are `text_denoise`, `image_denoise`, `video_denoise`, `image_text_pair_denoise`, and `auto_denoise`. `--name` must be snake_case and becomes the registry name used by workflow `steps[].operator`.

#### BaseOperator Contract

A custom operator file must provide at least one class that inherits from `denoise_workflow_engine.operators.base.BaseOperator`:

```python
from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


class MyTextFilterOperator(BaseOperator):
    operator_name = "my_text_filter"
    operator_version = "1.0.0"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        text = str(item.get("payload", {}).get("text", ""))
        if "advertisement" in text.lower():
            self.add_issue(item, "custom_advertisement")
            self.set_metric(item, "custom_advertisement_hit", True)
            item["action"] = "drop"
        return item
```

Core conventions:

- `operator_name` must be unique and must not duplicate a built-in operator; duplicate names fail during registry construction.
- `operator_name` must be snake_case, start with a letter, and use only lowercase letters, digits, and underscores.
- `process(item)` receives and returns the same DataItem dictionary, preserving core fields such as `id`, `payload`, `meta`, `metrics`, `issues`, and `operator_trace`.
- Use `self.add_issue(item, "issue_name")` to write issue tags. Tags appear in sample `issues` and in `metrics.json` `issue_distribution`.
- Use `self.set_metric(item, "metric_name", value)` to write evidence metrics. Metrics are emitted with samples in `clean.jsonl`, `dropped.jsonl`, or `review.jsonl`.
- Write `item["quality_score"]` or `metrics["quality_score"]` when the end-to-end operator's internal quality gate should route by `keep_score`, `review_score`, and `hard_fail_issues`.
- Use `item["intermediate"]` for OCR, ASR, key-frame, model response, or other internal evidence used inside the same end-to-end operator.
- If an operator raises an exception, the executor catches it, appends `operator_failed`, and routes the sample to `review`.

#### Development Focus by End-to-End Operator Type

Text end-to-end operators read `payload.text` and internally handle normalization, sensitive information governance, low-quality filtering, semantic scoring, and quality gating.

Image end-to-end operators read `payload.image_path` and internally handle decoding, resolution, blur, exposure, noise, watermark, logo, safety, repair, and quality gating.

Video end-to-end operators read `payload.video_path` and internally handle probing, decoding, key frames, audio, subtitle OCR, ASR, AIGC, audio-visual consistency, repair, and quality gating.

Image-text pair end-to-end operators read `payload.text` and `payload.image_path` and internally handle structure completeness, OCR-text consistency, keyword/CLIP/VLM consistency, safety fusion, and quality gating.

Auto end-to-end operators read text, image, image-text pair, or video input, route internally, and call the corresponding processing flow.

#### Enable in a Workflow

Place platform-facing custom operators under `workflows/plugins/`, for example `workflows/plugins/my_text_denoise.py`. Relative paths in `custom_operators`, `input.path`, and `output.run_dir` are resolved from the workflow file directory, so the workflow should use `./plugins/my_text_denoise.py`, which points to `workflows/plugins/my_text_denoise.py`.

Minimal integration example:

```yaml
custom_operators:
  - ./plugins/my_text_denoise.py
steps:
  - id: my_text_denoise
    operator: my_text_denoise
    params:
      profile: default
      thresholds:
        keep_score: 0.75
        review_score: 0.55
```

`steps[].id` is the node ID for this workflow, `steps[].operator` must match the end-to-end operator class `operator_name`, and `steps[].params` is passed as `self.config`. A main workflow should configure a single end-to-end operator step; preprocessing, model calls, scoring, and gating should be orchestrated inside that end-to-end operator.

#### External Dependency Preconditions

External models, OCR, ASR, CLIP, VLM, and video tools are not automatically provided by the command-line. Enable them only after their preconditions are met:

- LLM/VLM/OCR/CLIP/ASR: configure `*_API_KEY`, `*_API_BASE`, `*_MODEL`, and endpoint path variables based on `configs/api.env.example`, then reference those environment variable names in operator `params`.
- Remote model endpoints accept only `http` or `https` URLs with a valid host. Text, vision, and audio clients validate the final endpoint before sending a request.
- OCR/ASR: use real services that return parseable OCR text or transcription text; do not put `precomputed_ocr_text` or `precomputed_asr_text` answer hints in input data.
- ffmpeg/ffprobe: video probing, decoding, key-frame extraction, audio extraction, and repair depend on executable `ffmpeg` and `ffprobe` on the system PATH.
- When a dependency is unavailable, operators should write explicit `issues` and `metrics` so the end-to-end operator's internal quality gate or manual review can handle the sample, instead of silently treating it as passed.

#### Minimal Sample Validation

Before delivery to the platform, run at least one full small-sample validation:

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
uv run denoise run -c workflows/denoise_auto.yaml
uv run denoise report -t outputs/latest
```

Acceptance points:

- `validate` prints `workflow config is valid`, proving `custom_operators` can be imported, `operator_name` can be registered, and `steps` can be instantiated.
- `run` prints `workflow_id`, `total`, `keep`, `drop`, `review`, `failed`, and `report`.
- `outputs/latest/metrics.json` contains totals, routing counts, failure counts, concurrency information, and `issue_distribution`.
- Samples in `clean.jsonl`, `dropped.jsonl`, and `review.jsonl` contain `issues`, `metrics`, `operator_trace`, `action`, and `quality_score`.
- Key evidence from custom operators must be visible in sample-level `metrics` or `issues`; routing decisions must be explainable from `operator_trace`, `quality_score`, and end-to-end operator parameters.

### Project Structure

```text
DataStudio-AllModalIntelligentDataDenoising/
├── pyproject.toml                         # Package metadata, dependencies, and denoise script entry
├── uv.lock                                # uv lock file
├── example_data/                          # Public delivery sample input and assets
│   ├── input.jsonl                        # Public sample input used by the main workflow
│   └── assets/                            # Public image and video sample assets
├── configs/
│   └── api.env.example                    # External model API environment example
├── workflows/                             # Production workflow plus auxiliary validation workflows
│   ├── denoise_auto.yaml                  # Public production auto-routing workflow
│   ├── local_real_smoke.yaml              # Public sample smoke workflow
│   ├── video_aigc_detect_smoke.yaml       # Video AIGC detection smoke workflow
│   └── ...                                # Additional public validation and regression workflows
├── docs/                                  # Documentation directory; the current delivery includes the workflow configuration guide
├── tests/                                 # Unit tests, real-sample fixtures, and workflow validation
└── src/denoise_workflow_engine/
    ├── cli/main.py                        # command-line subcommand entry point
    ├── __main__.py                        # python -m denoise_workflow_engine entry point
    ├── schemas/                           # Input, output, and workflow JSON Schemas
    ├── runtime/                           # Workflow loading, input adaptation, execution, reporting, registry
    ├── utilities/                         # Pure helper modules: config assembly, stage orchestration, modality bases
    │   ├── config.py                      # Workflow-to-runtime config assembly
    │   ├── pipeline.py                    # Internal stage execution and trace helpers
    │   ├── image/
    │   │   ├── base.py                    # Image helper base
    │   │   └── decode.py                  # Image decoding helper
    │   ├── text/
    │   │   └── base.py                    # Text helper base
    │   ├── video/
    │   │   └── base.py                    # Video helper base
    │   └── image_text_pair/
    │       └── base.py                    # Image-text pair helper base
    └── operators/
        ├── __init__.py                    # Unified exports for built-in end-to-end operators
        ├── base.py                        # Operator base class
        ├── common/                        # Cross-modality shared capabilities such as leakage, routing, quality gate
        ├── text_denoising/                # Text denoising implementation
        │   ├── operator.py                # Workflow-facing entry class
        │   ├── pipeline.py                # End-to-end orchestration
        │   ├── assessors/                 # Assessment capabilities
        │   ├── governors/                 # Governance and repair capabilities
        │   └── pipelines/                 # Text sub-pipelines
        ├── image_denoising/               # Image denoising implementation: operator.py + pipeline.py + internal stages
        ├── image_text_pair_denoising/     # Image-text pair denoising implementation: operator.py + pipeline.py + internal stages
        ├── video_denoising/               # Video denoising implementation: operator.py + pipeline.py + internal stages
        └── auto_denoising/                # Auto-routing denoising implementation: operator.py + pipeline.py
```

The current built-in end-to-end operator convention is:

- `operators/__init__.py` provides the unified exports for workflow-registered built-in end-to-end operators.
- Inside each modality directory, `operator.py` defines the workflow-facing entry class and `pipeline.py` owns the end-to-end orchestration.
- Shared base classes, config assembly, path resolution, and lightweight helpers are consolidated under `utilities/` instead of staying mixed into workflow-facing operator paths.
- `operators/common/` is reserved for cross-modality shared capabilities; modality-specific behavior stays in the corresponding `*_denoising/` directories.

### Path Security Contract

The command entrypoints convert workflow config and `--allow-root` values to standard path objects during argument parsing. Input paths, record-level file fields, file-based `custom_operators`, and `output.run_dir` enter the same authorized-root boundary through standard path resolution. The current working directory is authorized by default; `--allow-root` accepts an existing directory and can be repeated. All four configurable output files are resolved before any file is opened and must remain inside the canonical `output.run_dir`; internal stages inherit the same authorization context through `_runtime`, and repair artifacts and video intermediates use constrained child paths. Programmatic calls can pass `allowed_roots` to `resolve_path`, `InputAdapter`, and `WorkflowExecutor` to enable the same boundary. Module-based custom operators execute Python import logic and must reference modules from a trusted environment.

### Testing

Use `uv` to run tests:

```bash
uv run pytest
```

Run focused subsets:

```bash
uv run pytest tests/test_flexible_input_custom_operator.py
uv run pytest tests/test_text_sensitive_layers.py tests/test_text_mac_address_layers.py
uv run pytest tests/test_video_aigc_operator.py
```

Existing tests cover:

- JSON, JSONL, CSV, directory, file, and raw-text input adaptation
- Custom operator template generation, loading, validation, and execution
- Workflow relative path resolution, checkpoint resume, and concurrent execution
- Layered sensitive text detection and masking
- Real-text MAC address regression samples
- Video AIGC operator and real-sample smoke workflow
- Common routing, quality gate, and selected image/image-text/video operator behavior
