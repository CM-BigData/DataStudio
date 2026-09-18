<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">QualityEvaluation</h1>

<p align="center">
  <strong>DataReady · Data Quality Evaluation</strong><br>
  Development Guide · Measure dataset quality with traceable scores and reports.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-quality--eval-0284c7.svg" alt="CLI: quality-eval">
</p>

<p align="center">
  <a href="../README.md">DataReady</a> &nbsp;·&nbsp;
  <a href="#dr-project-structure">Structure</a> &nbsp;·&nbsp;
  <a href="#dr-custom-operators">Custom Operators</a> &nbsp;·&nbsp;
  <a href="README.md">Usage Guide</a> &nbsp;·&nbsp;
  <a href="README_dev_zh.md">简体中文</a>
</p>

---

<details>
<summary><strong>On this page</strong></summary>

- [Overview](#dr-overview)
- [Project Structure](#dr-project-structure)
- [Validation Chain](#dr-validation-chain)
- [Developing Custom Operators](#dr-custom-operators)
- [Platform Integration Contract](#dr-platform-integration-contract)
- [Path Security Contract](#dr-path-security-contract)
- [Testing](#dr-testing)
- [Notes](#dr-notes)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

QualityEvaluation is a lightweight workflow-based data quality evaluation tool. The package name is `quality-eval-workflow-engine`, and the command entry point is `quality-eval`. The current implementation targets text and image datasets. It uses YAML/JSON workflows to call end-to-end operators for schema, completeness, length, abnormal characters, duplication, image format, resolution, blur, blank image, suspected AI-generated image, annotation bbox, and related checks. It writes sample-level results, summary JSON, Markdown reports, operator trace logs, checkpoints, and error queues.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `quality-eval` | [`text_dataset_eval.yaml`](workflows/text_dataset_eval.yaml) | Text · Image · Audio |

<a id="dr-project-structure"></a>

## Project Structure

```text
QualityEvaluation/
├── pyproject.toml              # Package metadata, dependencies, and quality-eval script entry
├── src/quality_eval/           # command-line, runtime, schemas, and end-to-end operators
├── workflows/                  # Text, CSV, image, and extension workflow examples
├── example_data/               # Public text and image sample data
├── real_data/                  # Real evaluation sample subsets for local extended validation only
├── src/quality_eval/schemas/   # Input, output, and workflow JSON Schemas
├── tests/                      # Tests for command-line, workflows, operators, tracing, and resume behavior
└── docs/                       # Documentation directory; the current delivery includes the workflow configuration guide
```

<a id="dr-validation-chain"></a>

## Validation Chain

After developing or integrating custom operators, use the real command-line to verify registration, configuration, execution, and report export in order:

```bash
uv run quality-eval --help
uv run quality-eval validate-config -c workflows/text_dataset_eval.yaml
uv run quality-eval run -c workflows/text_dataset_eval.yaml --task-id local_text --output-dir outputs/local_text
uv run quality-eval export-report -t outputs/local_text/text_eval_summary.json -o outputs/local_text/text_eval_report.md
```

`--help` confirms that the CLI entry point is available, `validate-config` confirms that `custom_operators`, `steps[].operator`, and input paths are usable, `run` generates sample results, summary, report, logs, errors, and checkpoint files, and `export-report` confirms that an existing summary can regenerate a Markdown report.

<a id="dr-custom-operators"></a>

## Developing Custom Operators

Custom operators connect text, image, scoring, or governance rules that are not built in yet to the same workflow engine. Developers deliver loadable Python operator files and minimal validation samples; the command-line entry point does not need to change.

### 1. Generate An Operator Template

Use the real command-line to generate templates. A project-local `plugins/` directory is recommended so workflows can load custom operators by relative path; this directory is not a built-in package directory and can be owned by the platform side.

```bash
mkdir -p plugins
uv run quality-eval operator-template --type text --name my_text_quality --output plugins/my_text_quality.py
uv run quality-eval operator-template --type image --name my_image_quality --output plugins/my_image_quality.py
uv run quality-eval operator-template --type score --name my_dataset_score --output plugins/my_dataset_score.py
uv run quality-eval operator-template --type governor --name my_quality_governor --output plugins/my_quality_governor.py
```

`--name` is written into the template class attribute `operator_name` and must be snake_case, for example `my_text_quality`. The workflow `steps[].operator` value must use the same name.

### 2. Implement BaseOperator

Each custom operator file must provide at least one class inheriting from `quality_eval.operators.common.base.BaseOperator` and implement `process(self, item)`. `BaseOperator` provides:

| Member | Usage |
|---|---|
| `operator_name` | Registered name, must be snake_case, and is referenced by `steps[].operator`. |
| `operator_version` | Version string included in operator trace/log output. |
| `self.config` | Merged workflow, runtime, step, and rules config. |
| `self.rules` | Shortcut to `rules` for thresholds, weights, and switches. |
| `setup(items, context)` | Optional hook for duplicate indexes, global statistics, or shared context. |
| `process(item)` | Required hook that processes one standard sample and returns it. |
| `teardown()` | Optional hook for releasing files, models, or connections. |
| `add_issue(item, code)` | Appends a deduplicated issue code. |
| `metric(item, key, value)` | Writes a sample-level metric. |

Minimal text operator example:

```python
from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator


class MyTextQualityOperator(BaseOperator):
    operator_name = "my_text_quality"
    operator_version = "1.0.0"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        text = str(item.get("payload", {}).get("text", ""))
        self.metric(item, "my_text_length", len(text))
        if len(text.strip()) < int(self.rules.get("my_min_length", 1)):
            self.add_issue(item, "my_text_too_short")
            item["action"] = "review"
        return item
```

Project AGENTS rules require Python comments and docstrings to be written in English. This README only shows a minimal snippet; delivered operators should follow that rule too.

### 3. Load And Use The Operator In A Workflow

`custom_operators` accepts Python file paths or module paths. Relative paths are resolved from the workflow file directory, so the recommended layout is a `plugins/` directory next to the workflow, or absolute paths for platform-managed plugins.

```yaml
workflow:
  id: custom_text_quality_eval
  task_type: text
input:
  type: raw_text
  text: Text to evaluate
output:
  result_path: ./outputs/custom_result.jsonl
  summary_path: ./outputs/custom_summary.json
  report_path: ./outputs/custom_report.md
rules:
  my_min_length: 10
custom_operators:
  - ./plugins/my_text_quality.py
steps:
  - id: custom_text_quality
    operator: my_text_quality
```

After wiring the workflow, run:

```bash
uv run quality-eval validate-config -c workflows/custom_text_quality.yaml
uv run quality-eval run -c workflows/custom_text_quality.yaml --task-id custom_text_quality --output-dir outputs/custom_text_quality
```

### 4. Text, Image, Scoring, And Governance Operator Boundaries

| Type | Recommended Input | Recommended Output |
|---|---|---|
| Text operator | `item["payload"]["text"]`, `meta.label`, and `self.rules` | Text length, format, character, semantic, or related `metrics`, plus explainable `issues`. |
| Image operator | `item["payload"]["image_path"]`, image `meta`, and annotations | Resolution, format, blur, blank-image, AIGC, bbox, or related `metrics` and `issues`. |
| Scoring operator | Existing `metrics`, `issues`, `score_weights`, or `rules` | `score`, `level`, and optional scoring breakdown metrics. |
| Governance operator | Existing `issues`, `score`, and business rules | `action` and `suggestions`, such as `keep`, `review`, or `drop`. |

Developers should keep issues, metrics, and scores explainable: use stable short codes in `issues`, record trigger evidence or key values in `metrics`, make `score` and `level` traceable to rules or metrics, and use `suggestions` for the next handling action.

<a id="dr-platform-integration-contract"></a>

## Platform Integration Contract

- Platform calls should use `quality-eval run -c <workflow> --task-id <workflow/task-id> --output-dir <workflow/output-dir>`, where `task-id` is stable and traceable.
- Custom operators should be centralized under `plugins/`, and workflows should declare them explicitly through `custom_operators` instead of relying on implicit imports.
- Operators must not implicitly change the input schema. They may add `metrics`, `issues`, `score`, `level`, `action`, `suggestions`, and `intermediate`, but should not remove or rename core fields such as `id`, `modality`, `source`, `payload`, or `meta`.
- `steps[].operator` references only `operator_name`, not the class name or file name.
- Before delivery, prepare minimal samples: `raw_text` or 1-3 JSONL/CSV rows for text operators, 1-3 images plus minimal `annotations.json` for image operators, and samples that trigger target `issues` for scoring/governance operators.
- Minimal validation must include `validate-config`, one `run`, checks for `summary/report/logs` outputs, and confirmation that `logs/<task_id>_operators.jsonl` contains the custom operator `operator` and `operator_version`.

<a id="dr-path-security-contract"></a>

## Path Security Contract

Command entrypoints convert filesystem options to standard path objects during argument parsing. `safe_path` and `safe_output_path` use standard path resolution for configured values and then constrain canonical results with `allowed_roots`. Command entrypoints authorize the current working directory by default. `run`, `validate-config`, `export-report`, and `operator-template` accept repeatable `--allow-root` options for other existing directories. Input normalization resolves record-level media paths through the executor resolver, and image paths in `image_folder` annotations use the same boundary. File-based `custom_operators` are checked before import, while module-based extensions must reference modules from a trusted environment. `validate_task_id` constrains task IDs to safe filename components and rejects Windows reserved device names; checkpoint, log, and error-queue paths receive a second containment check against their respective directories. Remote image-text consistency models require an immutable `image_text_consistency_model_revision` and load with `trust_remote_code=False`.

<a id="dr-testing"></a>

## Testing

```bash
cd QualityEvaluation
uv run pytest
```

Run narrower scopes:

```bash
uv run pytest tests/test_text_eval.py
uv run pytest tests/test_image_eval.py
uv run pytest tests/test_framework.py
```

The repository includes test files for command-line operator listing, workflow config validation, text JSONL/CSV evaluation, image evaluation, blank-image detection, suspected AIGC detection, punctuation and special-character operators, custom operators, trace logs, and resume audit fields. However, a direct `uv run pytest` currently fails during collection because duplicate test module names exist under both `clean_version/tests` and the root `tests/`.

<a id="dr-notes"></a>

## Notes

- This README only documents commands, workflows, operators, and files that exist in the current codebase. It does not describe an unimplemented server or interactive UI.
- Prefer the existing `example_data/` directory for public example validation. `real_data/` is intended only for local extended validation and should not be treated as the default delivery input.
- Workflow relative paths use two-stage resolution: workflow directory first, then project root.
- `--workers` overrides concurrency settings from workflow/runtime config. Multithreading is enabled only when both worker count and pending sample count are sufficient.
- `--resume` depends on existing result files and checkpoints. Reuse the same `--task-id` and output directory for resume runs.

<a id="dr-documentation"></a>

## Related Documentation

- [Usage guide](README.md) · [Development guide](README_dev.md)
- [Workflow configuration (Chinese)](docs/Workflow配置说明.md) · [Example workflows](workflows/)
- [Example data sources](example_data/SOURCES_en.md) · [Third-party licenses (Chinese)](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">Back to top</a> &nbsp;·&nbsp; <a href="../README.md">DataReady home</a>
</p>
