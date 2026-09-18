<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataDenoising</h1>

<p align="center">
  <strong>DataReady · Multimodal Data Denoising</strong><br>
  Usage Guide · Clean data and route samples for retention, removal, or review.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-denoise-0284c7.svg" alt="CLI: denoise">
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
- [Installation and Environment](#dr-installation)
- [Quick Start](#dr-quick-start)
- [Command-Line Usage](#dr-cli)
- [Input and Output](#dr-input-and-output)
- [Workflow Configuration](#dr-workflow-configuration)
- [Notes](#dr-notes)
- [Copyright and License](#dr-copyright-and-license)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

DataDenoising is a lightweight workflow engine for multimodal data cleaning and quality routing. It provides the `denoise` command-line entry point, reads text, image, image-text pair, and video samples from configurable inputs, runs built-in or custom denoising operators, and routes samples into keep, drop, and manual-review outputs.

The project package name is `denoise-workflow-engine`, the Python package path is `denoise_workflow_engine`, and the default production workflow is `workflows/denoise_auto.yaml`.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `denoise` | [`denoise_auto.yaml`](workflows/denoise_auto.yaml) | Text · Image · Image–text · Video |

<a id="dr-features"></a>

## Core Capabilities

- **End-to-end operator boundary**: the built-in registry exposes only five end-to-end operators: `text_denoise`, `image_denoise`, `image_text_pair_denoise`, `video_denoise`, and `auto_denoise`.
- **Automatic denoising orchestration**: `auto_denoise` internally performs leakage checks, modality routing, quality scoring, and action decisions without exposing intermediate workflow stages as operators.
- **Text denoising**: supports encoding detection, Unicode repair, Chinese normalization, HTML/Markdown cleanup, language detection, length/repetition/low-information-density filters, sensitive information detection and masking, semantic quality scoring, and text quality scoring.
- **Image denoising**: supports image decoding, size and aspect checks, blur/exposure/noise detection, QR code, watermark, logo, safety risk, subject completeness, visual quality scoring, and basic repair.
- **Image-text pair denoising**: supports structure checks, OCR interface, OCR-text consistency, key-field consistency, keyword similarity, CLIP/VLM consistency interfaces, safety fusion, and quality scoring.
- **Video denoising**: supports video probing, ffmpeg decoding, key-frame extraction, black/blur/freeze-frame/QR detection, audio extraction, audio quality, subtitle OCR, ASR interface, key-frame VLM, AIGC detection, audio-visual consistency, safety fusion, repair, and quality scoring.
- **Extensible workflows**: supports `pipeline` and `dag` workflow modes, custom operator files, checkpoint resume, sample-level concurrency, and Markdown report generation.

<a id="dr-installation"></a>

## Installation and Environment

### Requirements

- Python >= 3.10
- `uv` is recommended for environment management and command execution
- Video operators require local `ffmpeg` / `ffprobe`
- Main Python dependencies are listed in [`pyproject.toml`](pyproject.toml): `numpy`, `opencv-python`, `Pillow`, `PyYAML`, `requests`, `id-validator`, `phonenumbers`, `email-validator`, `python-stdnum`, `validators`, `lingua-language-detector`, `scikit-image`, `ImageHash`, `rapidfuzz`, and `regex`

### Local Setup

```bash
cd DataDenoising
uv sync
```

After installation, use the script entry point:

```bash
uv run denoise --help
```

You can also use the module entry point directly:

```bash
uv run python -m denoise_workflow_engine.cli.main --help
```

### Direct Command Invocation

If `denoise` is installed on the system `PATH`, invoke it directly:

```bash
denoise --help
```

If Windows PowerShell does not recognize `denoise`, activate the project virtual environment before invoking it:

```powershell
.\.venv\Scripts\Activate.ps1
denoise --help
```

### Optional Model API Configuration

The command-line loads local API environment variables during execution. The example file is:

```text
configs/api.env.example
```

Configure these OpenAI-compatible API variable groups as needed:

- `LLM_API_*`: text semantic quality and text repair
- `VLM_API_*`: image safety, image quality, image-text consistency, and video key-frame description
- `OCR_API_*`: image OCR and video subtitle OCR
- `CLIP_API_*`: image-text similarity interface
- `ASR_API_*`: video audio transcription interface, which requires a real audio transcription service

Every remote endpoint composed from `*_API_BASE` must use the `http` or `https` scheme and include a valid host name.

When external models are not configured, related operators use local fallback logic or conservative insufficient-evidence results.

<a id="dr-quick-start"></a>

## Quick Start

### 1. Prepare Input

The production workflow reads the public sample input from:

```text
example_data/input.jsonl
```

The repository now ships redistributable public samples for text, image, image-text pair, and video inputs, so `validate` and a public smoke run work out of the box. Replace them with production data while keeping one JSON object per JSONL line.

Each line is one JSON object. Minimal examples:

```jsonl
{"id":"text_001","payload":{"text":"Text content to denoise, long enough for quality assessment."}}
{"id":"image_001","payload":{"image_path":"example_data/assets/images/image_clean_dog.jpg"}}
{"id":"pair_001","payload":{"text":"Image caption text","image_path":"example_data/assets/images/image_clean_dog.jpg"}}
{"id":"video_001","payload":{"video_path":"example_data/assets/videos/video_clean.mp4"}}
```

Do not include answer or precomputed hint fields such as `expected_action`, `expected_clean`, `ground_truth`, `manifest`, `reference_image_path`, `image_keywords`, `precomputed_ocr_text`, or `precomputed_asr_text` in production input.

### 2. Validate the Workflow

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
```

Successful validation prints:

```text
workflow config is valid
```

### 3. Run Denoising

```bash
uv run denoise run -c workflows/denoise_auto.yaml
```

The command prints `workflow_id`, total count, keep/drop/review/failed counts, and the report path.

### 4. View the Report

```bash
uv run denoise report -t outputs/latest
uv run denoise report -t outputs/latest --show
```

<a id="dr-cli"></a>

## Command-Line Usage

### `denoise validate`

Validates workflow top-level structure, input configuration, step list, and operator names.

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
```

Arguments:

- `-c, --config`: workflow configuration path, required.
- `--allow-root`: authorizes access under an existing directory and can be repeated. The current working directory is authorized by default.

### `denoise run`

Runs a workflow.

```bash
uv run denoise run -c workflows/denoise_auto.yaml
uv run denoise run -c workflows/denoise_auto.yaml --resume
```

Arguments:

- `-c, --config`: workflow configuration path, required.
- `--resume`: resumes from `checkpoint.json`, skips completed samples, and appends to existing outputs.
- `--allow-root`: authorizes workflow input and output access under an existing directory and can be repeated. Canonical paths must stay under an authorized root.

### `denoise report`

Reads `metrics.json` and `report.md` from a run directory and prints a summary.

```bash
uv run denoise report -t outputs/latest
uv run denoise report -t outputs/latest --show
```

Arguments:

- `-t, --run-dir`: run directory containing `metrics.json`, required.
- `--show`: also prints the full `report.md`.

### `denoise operator-template`

Generates a loadable custom operator template.

```bash
mkdir -p workflows/plugins
uv run denoise operator-template --type text_denoise --name my_text_denoise --output workflows/plugins/my_text_denoise.py
```

Arguments:

- `--type`: end-to-end operator type, required; allowed values are `text_denoise`, `image_denoise`, `video_denoise`, `image_text_pair_denoise`, and `auto_denoise`.
- `--name`: snake_case operator name used in workflow steps, required.
- `--output`: output path for the generated Python file, required.

After generation, add it to the workflow:

```yaml
custom_operators:
  - ./plugins/my_text_denoise.py
steps:
  - id: my_text_filter
    operator: my_text_filter
    params: {}
```

### Path Boundary

`denoise validate` and `denoise run` access configs, inputs, and outputs under the current working directory by default. Workflow config and `--allow-root` command-line values are converted to standard path objects during argument parsing. Workflow-relative paths still resolve from the config directory and then receive canonical authorized-root checks; use `--allow-root <directory>` when the canonical target is outside the current working directory. The `image_path`, `video_path`, `audio_path`, `reference_image_path`, and `text_file` fields inside JSON, JSONL, CSV, and stdin records are also canonicalized and checked against authorized roots. Repair artifacts and video intermediates remain under the current `output.run_dir` or an explicitly authorized directory, and sample IDs are validated before use as filename components. File-based `custom_operators` must stay under an authorized root; module-based extensions must come from a trusted Python environment. `output.clean_path`, `output.dropped_path`, `output.review_path`, and `output.report_path` must also remain inside the canonical `output.run_dir`.

<a id="dr-input-and-output"></a>

## Input and Output

### Supported Input Types

`src/denoise_workflow_engine/schemas/workflow_schema.json` and `InputAdapter` support these `input.type` values:

- `auto`: detects by `input.path` shape and extension; when only `input.text` is present, it is treated as `raw_text`.
- `jsonl`: reads JSON line by line and turns invalid JSON lines into `invalid_json` review samples.
- `json`: reads a JSON object or array.
- `csv`: reads CSV rows and supports `id_field`, `text_field`, `image_field`, `video_field`, `audio_field`, and `modality_field` mappings.
- `directory`: recursively reads supported text, image, video, audio, and structured files under a directory.
- `file`: reads one file and detects text, image, video, audio, JSON, JSONL, or CSV by extension.
- `stdin`: reads from standard input.
- `raw_text`: reads `input.text` directly from the workflow.

A standard data item contains at least:

```json
{
  "id": "sample_id",
  "payload": {
    "text": "text content",
    "image_path": "example_data/assets/images/image_clean_dog.jpg",
    "video_path": "example_data/assets/videos/video_clean.mp4"
  }
}
```

When `payload.text` and `payload.image_path` are both present, the sample is processed as an image-text pair.

### Output Directory

The production workflow writes outputs to:

```text
outputs/latest/
  clean.jsonl
  dropped.jsonl
  review.jsonl
  metrics.json
  operator_logs.jsonl
  checkpoint.json
  report.md
```

Output samples follow `src/denoise_workflow_engine/schemas/output_schema.json`. Core fields include:

- `id`: sample ID
- `modality`: detected modality
- `payload`: cleaned or preserved business payload
- `metrics`: quality metrics written by operators
- `issues`: issue tag list
- `operator_trace`: operator-level execution trace
- `action`: `keep`, `drop`, `review`, or `pending`
- `quality_score`: quality score

Run summary follows `outputs/latest/metrics.json` and is shown in `outputs/latest/report.md`. Core fields include:

- `input_total_count` / `total_count`: total samples in the current input
- `current_run_count`: samples processed in the current run
- `historical_completed_count`: current-input samples completed by previous checkpoints
- `newly_processed_count`: samples newly processed in this run
- `current_completed_count`: completed samples in the current input
- `pending_count`: current-input samples still pending

<a id="dr-workflow-configuration"></a>

## Workflow Configuration

Production entry point:

```text
workflows/denoise_auto.yaml
```

This file is saved as `.yaml` while using JSON syntax. It contains:

- `workflow`: workflow metadata, including `id`, `name`, `mode`, `batch_size`, `concurrency`, and `checkpoint`
- `input`: input type, path, and field mappings
- `output`: run directory and output file names
- `custom_operators`: optional custom operator files or module paths
- `steps`: ordered operator list; `depends_on` can be used when `mode: dag`

See [`docs/Workflow配置说明.md`](docs/Workflow配置说明.md) for configuration details.

<a id="dr-notes"></a>

## Notes

- Production input should contain only data to process, not ground truth, expected actions, reference images, or precomputed OCR/ASR/keyword fields.
- Relative paths in `workflows/denoise_auto.yaml` are resolved from the workflow file directory; the public workflow now points to `../example_data/input.jsonl` and `../outputs/latest/`.
- `--resume` uses `checkpoint.json` in the output directory to skip completed samples and append to existing output files.
- External model API keys are not included. When APIs are not configured, operators do not assume remote capability is available.
- Video capabilities require executable `ffmpeg`/`ffprobe`; otherwise related video samples may enter review or failure counts.
- `denoise validate` checks configuration structure, input path, and operator construction. It is not a full execution.
- A sample written to `clean.jsonl` means the current workflow quality gate decided `keep`; it does not certify the sample has no historical risk.

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
