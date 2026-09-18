<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">QualityEvaluation</h1>

<p align="center">
  <strong>DataReady · Data Quality Evaluation</strong><br>
  Usage Guide · Measure dataset quality with traceable scores and reports.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-quality--eval-0284c7.svg" alt="CLI: quality-eval">
</p>

<p align="center">
  <a href="../README.md">DataReady</a> &nbsp;·&nbsp;
  <a href="#dr-quick-start">Quick Start</a> &nbsp;·&nbsp;
  <a href="#dr-cli">CLI</a> &nbsp;·&nbsp;
  <a href="README_dev.md">Development Guide</a> &nbsp;·&nbsp;
  <a href="README_zh.md">简体中文</a>
</p>

---

<details>
<summary><strong>On this page</strong></summary>

- [Overview](#dr-overview)
- [Core Capabilities](#dr-features)
- [Installation And Environment](#dr-installation)
- [Quick Start](#dr-quick-start)
- [Command-Line Usage](#dr-cli)
- [Input And Workflow Configuration](#dr-input-and-workflow-configuration)
- [Output](#dr-output)
- [Public End-To-End Operators](#dr-public-end-to-end-operators)
- [Usage: Running Evaluation Workflows As A Platform User](#dr-usage-running-evaluation-workflows-as-a-platform-user)
- [Copyright and License](#dr-copyright-and-license)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

QualityEvaluation is a lightweight workflow-based data quality evaluation tool. The package name is `quality-eval-workflow-engine`, and the command entry point is `quality-eval`. The current implementation targets text, image, and audio datasets. It uses YAML/JSON workflows to call end-to-end operators for schema, completeness, length, abnormal characters, duplication, image format, resolution, blur, blank image, suspected AI-generated image, annotation bbox, audio format, sample rate, bit depth, volume, noise, echo, and related checks. It writes sample-level results, summary JSON, Markdown reports, operator trace logs, checkpoints, and error queues.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `quality-eval` | [`text_dataset_eval.yaml`](workflows/text_dataset_eval.yaml) | Text · Image · Audio |

<a id="dr-features"></a>

## Core Capabilities

- **Text quality evaluation**: supports JSONL, CSV, and mapped flexible input fields, covering field completeness, text length, abnormal Unicode, low-quality repeated fragments, consecutive punctuation, special characters, punctuation pairing, text duplication, label completeness, and text scoring.
- **Image quality evaluation**: supports an image folder plus `annotations.json`, covering decode, lossless integrity, format allowlist, resolution, aspect ratio, blur, blank images, suspected AI-generated images, image-text consistency, duplicate images, label completeness, and bbox boundary checks.
- **Audio quality evaluation**: supports audio folders or table inputs, covering decode, format allowlist, sample rate, bit depth, volume dynamic range, clipping, noise, echo, duplicate audio, and audio scoring.
- **Workflow execution**: uses public end-to-end operator names in workflow steps, while internal checks are orchestrated inside the end-to-end operator.
- **Traceable output**: each sample result includes `trace_id`, `trace_summary`, and operator-level `trace`, while a separate operator log is also written.
- **Resume support**: `run --resume` reuses existing results and skips completed samples, with input total, current-run samples, historical completed samples, newly processed samples, current completed samples, and pending samples recorded separately.
- **Custom operators**: `operator-template` generates text, image, scoring, or governor operator templates, and workflows can load custom code through `custom_operators`.

<a id="dr-installation"></a>

## Installation And Environment

### Requirements

- Python >= 3.10
- Runtime dependencies: `PyYAML>=6.0`, `Pillow>=12.3.0`, `regex>=2026.5.9`
- Test dependency: `pytest>=8.0.0`, installed through the `test` optional dependency group.

### Local Setup

```bash
cd QualityEvaluation
uv sync
uv run quality-eval --help
```

If the installed script entry point is not used, run the module directly:

```bash
uv run python -m quality_eval --help
```

### Direct Command Invocation

If `quality-eval` is installed on the system `PATH`, invoke it directly:

```bash
quality-eval --help
```

If Windows PowerShell does not recognize `quality-eval`, activate the project virtual environment before invoking it:

```powershell
.\.venv\Scripts\Activate.ps1
quality-eval --help
```

<a id="dr-quick-start"></a>

## Quick Start

### 1. Validate Sample Workflows

```bash
uv run quality-eval validate-config -c workflows/text_dataset_eval.yaml
uv run quality-eval validate-config -c workflows/image_dataset_eval.yaml
```

On success, the command prints:

```text
valid_config=workflows/text_dataset_eval.yaml
```

### 2. Run Text Dataset Evaluation

```bash
uv run quality-eval run -c workflows/text_dataset_eval.yaml --task-id local_text --output-dir outputs/local_text
```

The command prints the main output paths:

```text
task_id=local_text
result_path=outputs/local_text/text_eval_result.jsonl
summary_path=outputs/local_text/text_eval_summary.json
report_path=outputs/local_text/text_eval_report.md
```

### 3. Run Image Dataset Evaluation

```bash
uv run quality-eval run -c workflows/image_dataset_eval.yaml --task-id local_image --output-dir outputs/local_image
```

<a id="dr-cli"></a>

## Command-Line Usage

```bash
quality-eval run -c <workflow.yaml> [--task-id <id>] [--output-dir <dir>] [--resume] [--workers <n>] [--allow-root <dir>]
quality-eval validate-config -c <workflow.yaml> [--allow-root <dir>]
quality-eval list-operators
quality-eval export-report -t <run-dir-or-summary-json> [-o <report.md>] [--allow-root <dir>]
quality-eval operator-template --type text|image|score|governor --name <snake_case_name> --output <file.py> [--allow-root <dir>]
```

### Subcommands

| Command | Description |
|---|---|
| `run` | Loads a workflow, runs the full quality evaluation, and writes results, summary, report, logs, checkpoint, and error queue. |
| `validate-config` | Validates workflow structure, operator registration names, and input paths. |
| `list-operators` | Prints currently registered operator names. |
| `export-report` | Regenerates a Markdown report from a summary JSON file or a run directory. |
| `operator-template` | Generates a custom operator template file. |

### Path Authorization

Subcommands that access filesystem paths stay under the current working directory by default. Repeat `--allow-root <directory>` to authorize another existing directory. Command-line path options are converted to standard path objects during argument parsing, while configured paths are canonicalized and checked against the authorized roots. Canonical config, input, output, report, record-level `image_path`/`audio_path`, image annotation, and file-based `custom_operators` paths must remain under the current working directory or an authorized directory. Module-based extensions must come from a trusted Python environment. `--task-id` accepts only letters, numbers, dots, underscores, and hyphens and rejects Windows reserved device names; the derived checkpoint, log, and error-queue files are constrained again to their output directories. Remote image-text consistency models require an audited immutable commit in `rules.image_text_consistency_model_revision`, and model loading does not execute remote custom code.

<a id="dr-input-and-workflow-configuration"></a>

## Input And Workflow Configuration

Workflows support YAML/JSON. Examples are stored in `workflows/`.

| Section | Description |
|---|---|
| `workflow` | Workflow id, name, execution mode, task type, batch settings, concurrency, and checkpoint switch. |
| `runtime` | Executor type, worker count, batch size, and retry count. |
| `input` | Input type and paths; text examples support `jsonl` and `csv`, and image examples use `image_folder`. |
| `output` | Sample result JSONL, summary JSON, and Markdown report paths. |
| `rules` | Quality thresholds and operator parameters. |
| `score_weights` | Comprehensive score weights. |
| `steps` | Workflow steps. Each `operator` must match a registered operator name. |

Text example:

```yaml
input:
  type: jsonl
  path: ./example_data/text_dataset.jsonl
```

CSV example:

```yaml
input:
  type: csv
  path: ./example_data/text_dataset.csv
```

Image example:

```yaml
input:
  type: image_folder
  path: ./example_data/image_dataset
  annotation_path: ./example_data/image_dataset/annotations.json
```

A unified input sample contains at least `id`, `modality`, `source`, `payload`, `meta`, `metrics`, `issues`, and `action`. Relative paths are resolved from the workflow file directory first; if the path does not exist there, the project root is used.

<a id="dr-output"></a>

## Output

`run` writes the files declared in the workflow `output` section. When `--output-dir` is used, configured filenames are preserved and only the directory is replaced.

| Artifact | Description |
|---|---|
| `*_result.jsonl` | Sample-level results, one JSON object per line. |
| `*_summary.json` | Dataset-level summary with counts, scores, issue distribution, sample lists, national-standard dimension mapping, and traceability information. |
| `*_report.md` | Markdown report generated from the summary JSON. |
| `checkpoints/<task_id>.json` | Resume checkpoint state. |
| `logs/<task_id>_operators.jsonl` | Operator-level execution trace log. |
| `errors/<task_id>_errors.jsonl` | Error queue for samples that hit operator exceptions. |

Sample-level output aligns with `src/quality_eval/schemas/output_schema.json`. Core fields include `task_id`, `sample_id`, `modality`, `status`, `score`, `level`, `metrics`, `issues`, `action`, and `suggestions`, with additional `trace_id`, `trace_summary`, and `trace` fields.

<a id="dr-public-end-to-end-operators"></a>

## Public End-To-End Operators

`src/quality_eval/operators/` only keeps end-to-end operators that workflow configs can call directly:

- `text_dataset_eval`: end-to-end text dataset quality evaluation, internally covering schema, completeness, length, character, duplication, punctuation, label, and scoring checks.
- `image_dataset_eval`: end-to-end image dataset quality evaluation, internally covering decoding, lossless integrity, format, resolution, aspect ratio, blur, duplication, annotation, blank-image, AIGC, image-text consistency, and scoring checks.
- `audio_dataset_eval`: end-to-end audio dataset quality evaluation, internally covering decoding, format, sample rate, bit depth, volume dynamic range, clipping, noise, echo, duplication, and scoring checks.

Single checks are internal workflow steps and are not exposed by `list-operators`. To run only part of the checks, declare them under the end-to-end operator `params.enabled_checks`, for example `blank`, `aigc`, `special_characters`, or `punctuation_pairing`.

Use the real command output as the source of truth:

```bash
uv run quality-eval list-operators
```

<a id="dr-usage-running-evaluation-workflows-as-a-platform-user"></a>

## Usage: Running Evaluation Workflows As A Platform User

Platform users do not need to change code. They only need input data, a workflow config, and an output directory.

1. Choose or copy a workflow, such as `workflows/text_dataset_eval.yaml` or `workflows/image_dataset_eval.yaml`.
2. Declare the data source under `input`; text commonly uses `jsonl`, `csv`, or `raw_text`, while image workflows commonly use `image_folder` plus `annotation_path`.
3. Declare one end-to-end evaluation step under `steps`; `steps[].operator` must be a registered name shown by `uv run quality-eval list-operators`.
4. Validate the config before running:

```bash
uv run quality-eval validate-config -c workflows/text_dataset_eval.yaml
```

5. Run the workflow with a stable platform task ID and output directory:

```bash
uv run quality-eval run -c workflows/text_dataset_eval.yaml --task-id <workflow-task-id> --output-dir <workflow-output-dir>
```

For platform integration, align `--task-id` with the platform task ID and `--output-dir` with the platform-owned result directory for that task. `--output-dir` preserves the filenames configured in `output.result_path`, `output.summary_path`, and `output.report_path`, while replacing their directory. One run writes `*_result.jsonl`, `*_summary.json`, and `*_report.md`, then derives `logs/<task_id>_operators.jsonl`, `errors/<task_id>_errors.jsonl`, and `checkpoints/<task_id>.json` next to the summary output directory.

After a summary exists, regenerate the Markdown report with:

```bash
uv run quality-eval export-report -t outputs/local_text/text_eval_summary.json -o outputs/local_text/text_eval_report.md
uv run quality-eval export-report -t outputs/local_text
```

<a id="dr-copyright-and-license"></a>

## Copyright and License

- This project is licensed under the MIT License. See [LICENSE](LICENSE).

<a id="dr-documentation"></a>

## Related Documentation

- [Usage guide](README.md) · [Development guide](README_dev.md)
- [Workflow configuration (Chinese)](docs/Workflow配置说明.md) · [Example workflows](workflows/)
- [Example data sources](example_data/SOURCES_en.md) · [Third-party licenses (Chinese)](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">Back to top</a> &nbsp;·&nbsp; <a href="../README.md">DataReady home</a>
</p>
