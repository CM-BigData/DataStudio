<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">MultimodalParsing</h1>

<p align="center">
  <strong>DataReady · Multimodal Content Parsing</strong><br>
  Usage Guide · Turn documents, images, and audio into structured content.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-parse-0284c7.svg" alt="CLI: parse">
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
- [Notes](#dr-notes)
- [Copyright and License](#dr-copyright-and-license)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

MultimodalParsing is a lightweight multimodal content parsing workflow engine. It uses YAML workflow files to orchestrate input adaptation, end-to-end parsing operators, and run reports. Markdown reconstruction, chunking, quality assessment, and other intermediate stages run inside the end-to-end operators. It is designed to convert PDF, Word, Excel, HTML, image, audio, and structured text inputs into unified JSONL parsing artifacts.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `parse` | [`pdf_parse.yaml`](workflows/pdf_parse.yaml) | PDF · Word · Excel · HTML · Image · Audio |

<a id="dr-features"></a>

## Core Capabilities

- **Configuration-driven workflows**: Define `workflow`, `input`, `output`, `steps`, and optional `custom_operators` in `workflows/*.yaml`.
- **Multimodal parsing**: Supports PDF, Word, Excel, HTML, image, and audio files, plus JSON, JSONL, CSV, stdin, and raw_text inputs.
- **End-to-end parsing operators**: `operators/` only exposes `pdf_parse`, `word_parse`, `excel_parse`, `html_parse`, `image_parse`, and `audio_parse`; extraction, OCR, ASR, Markdown reconstruction, chunking, and quality assessment are internal workflow stages.
- **Unified output format**: Each sample is emitted as a `DataItem` with `id`, `modality`, `source`, `payload`, `metrics`, `issues`, `artifacts`, and `action`.
- **Traceable runs**: Each run writes `artifacts.jsonl`, `failed.jsonl`, `metrics.json`, `report.md`, `workflow.yaml`, and `checkpoint.json`.
- **Resume and concurrency support**: `parse run` supports `--resume`, reads existing outputs from `output.path`, and skips completed samples; workflows can control sample-level concurrency through `workflow.concurrency`.
- **Custom operator extension**: `parse operator-template` generates custom operator templates, and workflows load them through `custom_operators`.

<a id="dr-installation"></a>

## Installation and Environment

### Requirements

- Python `>=3.10`; the local project `.python-version` currently specifies `3.13`.
- `uv` is recommended for environment synchronization and command execution.
- Runtime dependencies are managed in [`pyproject.toml`](pyproject.toml), including Click, Pydantic, PyYAML, python-docx, pandas, openpyxl, xlrd, Pillow, RapidOCR ONNX Runtime, soundfile, and the OpenAI SDK.
- Development test dependency: `pytest>=8.0`, installed through the `dev` optional dependency group.

### Local Setup

```bash
cd MultimodalParsing
uv sync
```

After installation, use the `parse` script or the module entrypoint:

```bash
uv run parse --help
uv run python -m parse_engine --help
```

### Direct Command Invocation

If `parse` is installed on the system `PATH`, invoke it directly:

```bash
parse --help
```

If Windows PowerShell does not recognize `parse`, activate the project virtual environment before invoking it:

```powershell
.\.venv\Scripts\Activate.ps1
parse --help
```

<a id="dr-quick-start"></a>

## Quick Start

### 1. Validate a Workflow Configuration

```bash
uv run parse validate -c workflows/pdf_parse.yaml
```

Successful output looks like:

```text
OK: pdf_parse_v1 (1 steps)
```

### 2. Run the Sample PDF Parser

```bash
uv run parse run -c workflows/pdf_parse.yaml
```

Public example workflows now read public sample inputs from `example_data/` and no longer depend on the removed internal `data/` directory.

The command prints the output directory, for example:

```text
MultimodalParsing/runs/pdf_parse
```

### 3. Read the Report and Trace a Sample

```bash
uv run parse report -t runs/pdf_parse
uv run parse trace --sample-id html40 -t runs/pdf_parse
```

`report` prints `report.md` from the output directory. `trace` searches `artifacts.jsonl` by sample id or artifact id and prints the matching JSON.

<a id="dr-cli"></a>

## Command-Line Usage

### Command Overview

```bash
uv run parse --help
```

The current command-line exposes these subcommands:

| Command | Purpose |
| --- | --- |
| `parse validate -c <workflow.yaml>` | Validate workflow configuration, input configuration, and operator references. |
| `parse run -c <workflow.yaml>` | Execute one parsing workflow and print the output directory. |
| `parse run -c <workflow.yaml> --resume` | Resume from `output.path` and skip already successful samples. |
| `parse operator-template --type <type> --name <name> --output <path>` | Generate a custom operator template. |
| `parse report -t <output_dir>` | Print `report.md` from an output directory. |
| `parse trace --sample-id <id> -t <output_dir>` | Query a sample or artifact JSON result. |

### Custom Operator Template

```bash
uv run parse operator-template \
  # mkdir -p workflows/plugins
  --type text \
  --name my_parse_operator \
  --output workflows/plugins/my_parse_operator.py
```

`--type` only accepts `document`, `image`, `audio`, `text`, and `quality_gate`. The generated Python file must be referenced through `custom_operators` in the workflow, and its snake_case operator name must be used in `steps[].operator`.

<a id="dr-input-and-output"></a>

## Input and Output

### Input Configuration

Workflow `input` supports these types:

| `input.type` | Description |
| --- | --- |
| `auto` | Infer the input type from `path` or `text`. |
| `file_dir` / `directory` | Recursively read supported non-hidden files in a directory. |
| `file` | Read one media, text, or structured file. |
| `json` | Read a JSON object or array. |
| `jsonl` | Read JSONL/NDJSON line by line. |
| `csv` | Read CSV by header; each row becomes one sample. |
| `stdin` | Read plain text or JSON from standard input. |
| `raw_text` | Create one sample directly from `input.text`. |

Supported media suffixes include `.pdf`, `.docx`, `.xls`, `.xlsx`, `.html`, `.htm`, `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.wav`, `.mp3`, `.m4a`, `.flac`, and `.aac`.

Structured inputs can use field mappings:

```yaml
input:
  type: csv
  path: data/input.csv
  id_field: sample_id
  modality_field: modality
  path_field: file_path
  text_field: content
```

### Example Workflow

```yaml
workflow:
  id: pdf_parse_v1
  name: PDF 内容解析流程
  mode: pipeline
  batch_size: 8
  concurrency: 1
  checkpoint: true

input:
  type: file_dir
  path: example_data/pdf

output:
  type: jsonl
  path: runs/pdf_parse
  report_path: runs/pdf_parse/report.md

steps:
  - id: pdf_parse
    operator: pdf_parse
    params:
      layout:
        min_chars: 24
```

The project includes `workflows/pdf_parse.yaml`, `workflows/word_parse.yaml`, `workflows/excel_parse.yaml`, `workflows/html_parse.yaml`, `workflows/image_parse.yaml`, and `workflows/audio_parse.yaml` as public example workflows.

### Output Files

Each `parse run` writes these files directly under `output.path`:

| File | Description |
| --- | --- |
| `artifacts.jsonl` | One `DataItem` per line, containing parsing artifacts for each sample. |
| `failed.jsonl` | Samples whose `action == "failed"` only. |
| `metrics.json` | Totals, modality distribution, artifact types, issue types, concurrency, and resume statistics. |
| `report.md` | Markdown summary report with the title `Content Parsing Report`. |
| `workflow.yaml` | Copy of the workflow configuration used for this run. |
| `checkpoint.json` | Run status, completed samples, and resume metadata. |

Run summary follows `output.path/metrics.json` and is shown in `output.path/report.md`. Core fields include:

- `input_total_count`: total samples in the current input
- `total`: samples processed in the current run
- `historical_completed_count`: current-input samples completed by previous outputs
- `newly_processed_count`: samples newly processed in this run
- `current_completed_count`: completed samples in the current input
- `pending_count`: current-input samples still pending

One `DataItem` follows the core structure in `src/parse_engine/schemas/output_schema.json`:

```json
{
  "id": "demo",
  "modality": "pdf",
  "source": {"path": "example_data/pdf/html40.pdf", "format": "pdf"},
  "payload": {"path": "example_data/pdf/html40.pdf"},
  "metrics": {},
  "issues": [],
  "artifacts": [],
  "action": "parsed"
}
```

<a id="dr-notes"></a>

## Notes

- The internal ASR stage in `audio_parse` only reads the current workflow `steps[].params.asr` block. The default example workflow targets DashScope `qwen3-asr-flash` and reads credentials from `DASHSCOPE_API_KEY`; when the backend is unavailable, it records an `asr_not_configured` issue and does not generate placeholder transcript text.
- `pdf_parse` and `image_parse` now default to workflow `params.document_parse` with the `openai_compatible` provider; switch to `provider: ocrflux` when an OCRFlux deployment is available. OCRFlux cross-page merge responses use safe literal parsing with index-pair type and page-bound validation.
- `.doc` or fake `.docx` handling in `word_parse` requires workflow-level `params.structure.soffice_command` and `params.media.soffice_command` values that point to the LibreOffice command.
- Directory input only reads supported non-hidden files and sorts paths to keep output stable.
- Relative `input.path` and `output.path` are resolved against the project directory one level above the workflow file directory.
- `report_path` is currently retained as a configuration field; the executor writes the actual report to `report.md` in the output directory.
- `trace` accepts `output.path`.
- Custom operator `operator_name` values must be snake_case and must match the workflow `steps[].operator` value.

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
