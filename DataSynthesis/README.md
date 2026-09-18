<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataSynthesis</h1>

<p align="center">
  <strong>DataReady · High-Quality Data Synthesis</strong><br>
  Usage Guide · Generate text, images, structured records, and multimodal samples.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-synthesis-0284c7.svg" alt="CLI: synthesis">
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
- [Run a Data Generation Workflow](#dr-run-a-data-generation-workflow)
- [Input and Output](#dr-input-and-output)
- [Built-in Workflows and Operators](#dr-built-in-workflows-and-operators)
- [Notes](#dr-notes)
- [Development Guide](#dr-development-guide)
- [Copyright and License](#dr-copyright-and-license)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

DataSynthesis is a lightweight workflow engine for high-quality data synthesis tasks. It uses YAML workflows to orchestrate input adaptation, text/image/structured data synthesis, end-to-end synthesis operators, internal quality loops, retry, resume, and report generation. After installation, it exposes the `synthesis` command-line entry point.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `synthesis` | [`structured_synthesis.yaml`](workflows/structured_synthesis.yaml) | Text · Image · Structured · Multimodal |

<a id="dr-features"></a>

## Core Capabilities

- **Workflow-driven execution**: Declare `workflow`, `input`, `output`, `steps`, and optional `custom_operators` in `workflows/*.yaml`.
- **Multiple input types**: Supports `seed_yaml`, `jsonl`, `json`, `csv`, `directory`, `file`, `stdin`, `raw_text`, and `auto` detection for common file types.
- **Built-in synthesis operators**: Covers text synthesis, image-model synthesis, structured-record synthesis, text QA, table QA, synonym replacement, question augmentation, and multimodal synthesis.
- **Quality loop**: Validation, diversity, safety filtering, and quality gating run as internal stages inside end-to-end operators and are not exposed as public workflow operators.
- **Utility boundary**: `src/synthesis_engine/utilities/` is reserved for pure helpers such as diversity signatures, structured synthesis helpers, and image prompt/validation helpers. Business orchestration entry points such as the text mapper retry pipeline stay with the capability package at `src/synthesis_engine/operators/text_synthesis/pipeline.py`.
- **Traceable runs**: Each run writes the workflow copy, JSONL outputs, metrics, report, and checkpoint under `output.path`, which makes serial tool chaining straightforward.
- **Custom extension**: Use `synthesis operator-template` to generate a custom operator template and load it through workflow `custom_operators`.

<a id="dr-installation"></a>

## Installation and Environment

### Requirements

- Python >= 3.10
- `uv` is recommended
- Runtime dependencies from [`pyproject.toml`](pyproject.toml): `click`, `openai`, `PyYAML`, `Pillow`, `tenacity`, `httpx[socks]`
- Development test dependency: `pytest`

### Local Setup

```bash
cd DataSynthesis
uv sync
uv run synthesis --help
```

### Direct Command Invocation

If `synthesis` is installed on the system `PATH`, invoke it directly:

```bash
synthesis --help
```

If Windows PowerShell does not recognize `synthesis`, activate the project virtual environment before invoking it:

```powershell
.\.venv\Scripts\Activate.ps1
synthesis --help
```

Text LLM workflows call OpenAI-compatible services through the official `openai` SDK and read settings from `model_config` or `configs/model_registry.yaml`. Common environment variables are:

```bash
export LLM_API_BASE=<openai-compatible-base-url>
export LLM_API_KEY=<api-key>
```

When an API key is sent to a remote OpenAI-compatible service, `LLM_API_BASE` must use HTTPS. HTTP is accepted only for local compatible services on `localhost`, `127.0.0.1`, or `::1`. The image-synthesis and question-augmentation examples read the endpoint from `LLM_API_BASE` and the credential from `OPENAI_API_KEY`.

Structured-record, template-text, and synonym-replacement workflows can run without an external LLM. Real model workflows such as `text_llm_synthesis`, image synthesis, multimodal synthesis, and question augmentation require valid model configuration.

<a id="dr-quick-start"></a>

## Quick Start

### 1. Validate a Workflow

```bash
uv run synthesis validate -c workflows/structured_synthesis.yaml
```

Successful output looks like:

```text
OK: structured_synthesis_v1 (7 steps)
```

### 2. Run a Workflow

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml
```

The command prints the output directory, for example:

```text
/path/to/DataSynthesis/runs/structured_synthesis
```

### 3. Print the Report

```bash
uv run synthesis report -t runs/structured_synthesis
```

`report` reads `report.md` directly from `output.path`.

### 4. Trace a Sample

```bash
uv run synthesis trace -t runs/structured_synthesis --sample-id record_dataset_source
```

`trace` searches `generated.jsonl` and `filtered.jsonl` and prints the matching sample as formatted JSON.

<a id="dr-cli"></a>

## Command-Line Usage

The installed script entry point is `synthesis = synthesis_engine.cli.main:cli`.

```bash
synthesis [OPTIONS] COMMAND [ARGS]...
```

| Command | Purpose | Key options |
| --- | --- | --- |
| `validate` | Validate workflow configuration, input path, and operator creatability | `-c, --config PATH` |
| `run` | Execute a workflow and print the output directory | `-c, --config PATH`, `--resume` |
| `operator-template` | Generate a custom operator template | `--type text\|image\|structured\|quality_gate`, `--name`, `--output` |
| `report` | Print `report.md` from an output directory | `-t, --task PATH` |
| `trace` | Query a generated or filtered result by sample ID | `--sample-id TEXT`, `-t, --task PATH` |

### Resume a Run

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml --resume
```

Resume mode reads the existing `generated.jsonl`, skips samples already marked as `accepted`, and updates checkpoint and metrics.

### Generate a Custom Operator Template

```bash
mkdir -p workflows/plugins
uv run synthesis operator-template --type text --name my_synthesis_operator --output workflows/plugins/my_synthesis_operator.py
```

The generated Python file can be loaded by a workflow:

```yaml
custom_operators:
  - ./plugins/my_synthesis_operator.py
steps:
  - id: custom
    operator: my_synthesis_operator
    params: {}
```

The custom operator `operator_name` must use snake_case.

<a id="dr-run-a-data-generation-workflow"></a>

## Run a Data Generation Workflow

Prepare a workflow, seed data, and an output directory; no Python code changes are needed. A typical layout keeps workflows under `workflows/`, input samples under `example_data/` or a local data directory, and runtime artifacts under the directory configured by `output.path`.

### Integration Contract

| Configuration | Contract |
| --- | --- |
| `workflow` | Declares runtime metadata such as `id`, `name`, `batch_size`, `concurrency`, `checkpoint`, and `retry_limit` |
| `input` | Declares the seed source; common usage is `type: seed_yaml` + `path: example_data/**/*.yaml`, with JSONL, JSON, CSV, directory, file, stdin, and raw text also supported |
| `output.path` | Output directory; `run` writes directly into this directory |
| `steps[].operator` | References the `operator_name` of a built-in or custom operator; YAML step order is execution order |
| `custom_operators` | Optional; loads custom Python files or modules |

A minimal seed should contain one sample for smoke testing:

```yaml
items:
  - id: smoke_structured_001
    task_type: structured
    prompt: Generate one customer support ticket.
    payload:
      schema:
        - name: ticket_id
          type: string
          prefix: ticket
```

First validate configuration and operator creatability:

```bash
uv run synthesis validate -c workflows/structured_synthesis.yaml
```

Then run the workflow:

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml
```

After the run finishes, read artifacts from the output directory:

| File | Purpose |
| --- | --- |
| `generated.jsonl` | Deliverable data; only samples with `action=accepted` |
| `filtered.jsonl` | Audit data; samples with `action=filtered` or `action=failed` |
| `metrics.json` | Totals, task types, action distribution, quality scores, concurrency stats, and resume stats |
| `report.md` | Human-readable summary report |
| `workflow.yaml` | Copy of the workflow used for this run |
| `checkpoint.json` | Resume checkpoint state |

Use these commands to inspect the report and trace one sample:

```bash
uv run synthesis report -t runs/structured_synthesis
uv run synthesis trace -t runs/structured_synthesis --sample-id record_dataset_source
```

### Models and Credentials

Text LLM operators first read step `params.model_config`; otherwise they resolve `model_ref` from `configs/model_registry.yaml`. The current examples use OpenAI-compatible environment variables:

```bash
export LLM_API_BASE=<openai-compatible-base-url>
export LLM_API_KEY=<api-key>
```

Remote OpenAI-compatible endpoints must use HTTPS when carrying an API key; loopback endpoints may use HTTP. `workflows/image_synthesis.yaml` and `workflows/text_question_augmentation.yaml` use `LLM_API_BASE` and `OPENAI_API_KEY`.

Structured-record, template-text, and some offline rewrite workflows do not require external credentials. Image synthesis requires a configured text-to-image model. Without credentials, start with `validate` or local workflows such as `workflows/structured_synthesis.yaml`, then use a minimal seed to confirm that `generated.jsonl`, `metrics.json`, and `report.md` are produced.

### Prompt Template Library

The prompt template library defaults to `src/synthesis_engine/prompts/`. Each template file is YAML and should at least define top-level `system` and `user` fields; structured templates with `metadata`, `messages`, and `output_schema` are also supported. Template bodies can reference variables such as `{{ seed_id }}`, `{{ prompt }}`, `{{ topic }}`, `{{ audience }}`, `{{ style }}`, `{{ question }}`, and `{{ text }}`.

You can override the default prompt directory or template name through step parameters:

```yaml
steps:
  - id: text_synthesis
    operator: text_synthesis
    params:
      stages:
        text_llm_synthesis:
          prompt_template: instruction_generation
          prompt_dir: ./prompts
```

Minimal template example:

```yaml
system: |
  You are a data synthesis model.
user: |
  Seed id: {{ seed_id }}
  Source prompt: {{ prompt }}
  Topic: {{ topic }}
```

Current boundaries:

- When `prompt_dir` is omitted, the operator automatically uses the built-in prompt library.
- When `prompt_template` does not exist, execution fails with a clear missing-template file error so misconfiguration can be caught early.
- The prompt library is currently wired into `text_llm_synthesis`, `question_decomposition`, `question_augmentation`, and `text_rewrite`.
- `question_augmentation` chooses `question_augmentation_en` or `question_augmentation_zh` from `language` by default, and still allows an explicit `prompt_template` override.
- Multimodal and image-generation prompts still live in their own implementations. Future consolidation can reuse the same YAML template convention.

<a id="dr-input-and-output"></a>

## Input and Output

### Workflow Configuration

A minimal workflow has this shape:

```yaml
workflow:
  id: structured_synthesis_v1
  name: Structured data synthesis workflow
  mode: pipeline
  batch_size: 8
  concurrency: 1
  checkpoint: true
  retry_limit: 1

input:
  type: seed_yaml
  path: example_data/structured/structured_schema.yaml

output:
  type: jsonl
  path: runs/structured_synthesis
  report_path: runs/structured_synthesis/report.md

steps:
  - id: analyze_distribution
    operator: structured_synthesis
    params: {}
```

`workflow.concurrency` controls sample-level concurrency. When an operator allows concurrency and there are multiple active samples, the executor uses a thread pool and preserves input order.

### Input Samples

`seed_yaml` input uses an `items` list:

```yaml
items:
  - id: record_customer_ticket
    task_type: structured
    prompt: Generate one synthetic customer support ticket record.
    payload:
      schema:
        - name: ticket_id
          type: string
          prefix: ticket
```

Normalized samples contain:

| Field | Description |
| --- | --- |
| `id` | Sample ID; generated from line number, file name, or timestamp when missing |
| `task_type` | `text`, `image`, or `structured` |
| `prompt` | Original synthesis intent |
| `payload` | Business fields such as schema, topic, image path, and similar data |
| `lineage` | Input source, seed ID, retry history, and other trace metadata |

JSON, JSONL, and CSV inputs can map fields explicitly through `id_field`, `task_type_field`, and `prompt_field`. Unmapped extra fields are preserved under `payload`.

### Output Files

Each `run` writes directly under `output.path`:

| File | Content |
| --- | --- |
| `workflow.yaml` | Copy of the workflow used for this run |
| `generated.jsonl` | Deliverable samples with `action=accepted` |
| `filtered.jsonl` | Audit samples with `action=filtered` or `action=failed` |
| `metrics.json` | Totals, task types, actions, issue types, average quality/diversity scores, resume stats, and concurrency stats |
| `report.md` | Markdown summary report |
| `checkpoint.json` | Run status, completed samples, skipped count, and checkpoint metadata |

Run summary follows `output.path/metrics.json` and is shown in `output.path/report.md`. Core fields include:

- `input_total_count`: total samples in the current input
- `total`: samples processed in the current run
- `historical_completed_count`: current-input samples completed by previous outputs
- `newly_processed_count`: samples newly processed in this run
- `current_completed_count`: completed samples in the current input
- `pending_count`: current-input samples still pending

Each output sample is the JSON form of `GenerationItem`, mainly including `id`, `task_type`, `prompt`, `payload`, `generated`, `metrics`, `issues`, `action`, and `lineage`.

<a id="dr-built-in-workflows-and-operators"></a>

## Built-in Workflows and Operators

| Example workflow | Input | Purpose |
| --- | --- | --- |
| `workflows/text_synthesis.yaml` | `example_data/text/text_topics.yaml` | Generate instruction/input/output text samples with `text_llm_synthesis` |
| `workflows/structured_synthesis.yaml` | `example_data/structured/structured_schema.yaml` | Generate structured records from field schemas and validate them |
| `workflows/image_synthesis.yaml` | `example_data/image/image_prompts.yaml` | Call a text-to-image model to generate PNG images and validate dimensions |
| `workflows/text_qa_synthesis.yaml` | `example_data/text/text_qa_sources.yaml` | Generate QA samples from text sources |
| `workflows/text_synonym_replacement.yaml` | `example_data/text/synonym_replacement_real_texts.yaml` | Run offline synonym replacement and rewrite validation |
| `workflows/text_question_augmentation.yaml` | `example_data/text/question_augmentation_real_questions.yaml` | Generate question-augmentation variants |
| `workflows/text_multimodal_synthesis.yaml` | `example_data/multimodal/multimodal_real_samples.yaml` | Run three-stage image-text multimodal synthesis |

<a id="dr-notes"></a>

## Notes

- `README_zh.md` is the Chinese documentation and `README.md` is the English documentation; keep them informationally aligned.
- Relative input paths are resolved from the project root above the workflow configuration directory.
- `report_path` is kept in configuration, but the executor currently writes the actual report to `report.md` under the output directory.
- `text_llm_synthesis`, multimodal synthesis, and some question-generation workflows depend on OpenAI-compatible LLM configuration. Without credentials, prefer non-LLM workflows or `validate` first.
- `generated.jsonl` only contains `accepted` samples that pass the quality gate. Filtered and failed samples are kept in `filtered.jsonl` for audit.
- `runs/` stores runtime artifacts. `run` creates new directories, so documentation checks should prefer `validate` and `--help` when you want to avoid extra artifacts.

<a id="dr-development-guide"></a>

## Development Guide

See the [development guide](README_dev.md) for project structure, custom operators, and testing.

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
