# DataStudio-HighQualityDataSynthesis

> 中文版本: [README_zh.md](README_zh.md)

DataStudio-HighQualityDataSynthesis is a lightweight workflow engine for high-quality data synthesis tasks. It uses YAML workflows to orchestrate input adaptation, text/image/structured data synthesis, end-to-end synthesis operators, internal quality loops, retry, resume, and report generation. After installation, it exposes the `synthesis` command-line entry point.

## Deployment and Usage Guide

### Core Capabilities

- **Workflow-driven execution**: Declare `workflow`, `input`, `output`, `steps`, and optional `custom_operators` in `workflows/*.yaml`.
- **Multiple input types**: Supports `seed_yaml`, `jsonl`, `json`, `csv`, `directory`, `file`, `stdin`, `raw_text`, and `auto` detection for common file types.
- **Built-in synthesis operators**: Covers text synthesis, image-model synthesis, structured-record synthesis, text QA, table QA, synonym replacement, question augmentation, and multimodal synthesis.
- **Quality loop**: Validation, diversity, safety filtering, and quality gating run as internal stages inside end-to-end operators and are not exposed as public workflow operators.
- **Utility boundary**: `src/synthesis_engine/utilities/` is reserved for pure helpers such as diversity signatures, structured synthesis helpers, and image prompt/validation helpers. Business orchestration entry points such as the text mapper retry pipeline stay with the capability package at `src/synthesis_engine/operators/text_synthesis/pipeline.py`.
- **Traceable runs**: Each run writes the workflow copy, JSONL outputs, metrics, report, and checkpoint under `output.path`, which makes serial tool chaining straightforward.
- **Custom extension**: Use `synthesis operator-template` to generate a custom operator template and load it through workflow `custom_operators`.

### Installation and Environment

#### Requirements

- Python >= 3.10
- `uv` is recommended
- Runtime dependencies from `pyproject.toml`: `click`, `openai`, `PyYAML`, `Pillow`, `tenacity`, `httpx[socks]`
- Development test dependency: `pytest`

#### Local Setup

```bash
cd DataStudio-HighQualityDataSynthesis
uv sync
uv run synthesis --help
```

#### Direct Command Invocation

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

### Quick Start

#### 1. Validate a Workflow

```bash
uv run synthesis validate -c workflows/structured_synthesis.yaml
```

Successful output looks like:

```text
OK: structured_synthesis_v1 (7 steps)
```

#### 2. Run a Workflow

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml
```

The command prints the output directory, for example:

```text
/path/to/DataStudio-HighQualityDataSynthesis/runs/structured_synthesis
```

#### 3. Print the Report

```bash
uv run synthesis report -t runs/structured_synthesis
```

`report` reads `report.md` directly from `output.path`.

#### 4. Trace a Sample

```bash
uv run synthesis trace -t runs/structured_synthesis --sample-id record_dataset_source
```

`trace` searches `generated.jsonl` and `filtered.jsonl` and prints the matching sample as formatted JSON.

### Command-Line Usage

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

#### Resume a Run

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml --resume
```

Resume mode reads the existing `generated.jsonl`, skips samples already marked as `accepted`, and updates checkpoint and metrics.

#### Generate a Custom Operator Template

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

### Run a Data Generation Workflow

Prepare a workflow, seed data, and an output directory; no Python code changes are needed. A typical layout keeps workflows under `workflows/`, input samples under `example_data/` or a local data directory, and runtime artifacts under the directory configured by `output.path`.

#### Integration Contract

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

#### Models and Credentials

Text LLM operators first read step `params.model_config`; otherwise they resolve `model_ref` from `configs/model_registry.yaml`. The current examples use OpenAI-compatible environment variables:

```bash
export LLM_API_BASE=<openai-compatible-base-url>
export LLM_API_KEY=<api-key>
```

Remote OpenAI-compatible endpoints must use HTTPS when carrying an API key; loopback endpoints may use HTTP. `workflows/image_synthesis.yaml` and `workflows/text_question_augmentation.yaml` use `LLM_API_BASE` and `OPENAI_API_KEY`.

Structured-record, template-text, and some offline rewrite workflows do not require external credentials. Image synthesis requires a configured text-to-image model. Without credentials, start with `validate` or local workflows such as `workflows/structured_synthesis.yaml`, then use a minimal seed to confirm that `generated.jsonl`, `metrics.json`, and `report.md` are produced.

#### Prompt Template Library

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

### Input and Output

#### Workflow Configuration

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

#### Input Samples

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

#### Output Files

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

### Built-in Workflows and Operators

| Example workflow | Input | Purpose |
| --- | --- | --- |
| `workflows/text_synthesis.yaml` | `example_data/text/text_topics.yaml` | Generate instruction/input/output text samples with `text_llm_synthesis` |
| `workflows/structured_synthesis.yaml` | `example_data/structured/structured_schema.yaml` | Generate structured records from field schemas and validate them |
| `workflows/image_synthesis.yaml` | `example_data/image/image_prompts.yaml` | Call a text-to-image model to generate PNG images and validate dimensions |
| `workflows/text_qa_synthesis.yaml` | `example_data/text/text_qa_sources.yaml` | Generate QA samples from text sources |
| `workflows/text_synonym_replacement.yaml` | `example_data/text/synonym_replacement_real_texts.yaml` | Run offline synonym replacement and rewrite validation |
| `workflows/text_question_augmentation.yaml` | `example_data/text/question_augmentation_real_questions.yaml` | Generate question-augmentation variants |
| `workflows/text_multimodal_synthesis.yaml` | `example_data/multimodal/multimodal_real_samples.yaml` | Run three-stage image-text multimodal synthesis |

### Notes

- `README_zh.md` is the Chinese documentation and `README.md` is the English documentation; keep them informationally aligned.
- Relative input paths are resolved from the project root above the workflow configuration directory.
- `report_path` is kept in configuration, but the executor currently writes the actual report to `report.md` under the output directory.
- `text_llm_synthesis`, multimodal synthesis, and some question-generation workflows depend on OpenAI-compatible LLM configuration. Without credentials, prefer non-LLM workflows or `validate` first.
- `generated.jsonl` only contains `accepted` samples that pass the quality gate. Filtered and failed samples are kept in `filtered.jsonl` for audit.
- `runs/` stores runtime artifacts. `run` creates new directories, so documentation checks should prefer `validate` and `--help` when you want to avoid extra artifacts.

## Development Guide

### Project Structure

```text
DataStudio-HighQualityDataSynthesis/
├── configs/                  # Runtime and model registry configuration
├── example_data/             # Public minimal sample data and local images
├── docs/                     # Documentation directory; the current release includes the workflow configuration guide
├── scripts/                  # Local run scripts
├── src/synthesis_engine/
│   ├── schemas/              # Input, output, and workflow JSON Schemas
│   ├── cli/                  # Click command-line entry point
│   ├── accessors/            # LLM and retrieval QA accessors
│   ├── llm/                  # OpenAI-compatible client wrapper
│   ├── mappers/              # Text synthesis mapper layer
│   ├── operators/            # Text, image, structured, and quality operators
│   ├── prompts/              # Prompt templates
│   └── runtime/              # Config, input adapter, executor, registry, metrics, and report modules
├── tests/                    # pytest tests and real fixtures
├── workflows/                # Runnable workflow examples
├── pyproject.toml            # Package metadata, dependencies, and command-line entry point
└── uv.lock                   # uv lock file
```

### Developing Custom Operators

Package custom text, image, structured, or quality-gate logic as `BaseOperator` subclasses and load them through workflow `custom_operators`. A recommended layout is `workflows/plugins/`, for example `workflows/plugins/my_synthesis_operator.py`. The workflow should then reference the file as `./plugins/my_synthesis_operator.py`.

#### 1. Generate a Template

```bash
mkdir -p workflows/plugins
uv run synthesis operator-template --type text --name my_synthesis_operator --output workflows/plugins/my_synthesis_operator.py
```

`--type` supports `text`, `image`, `structured`, and `quality_gate`. `--name` is written into the class attribute `operator_name`; it must be snake_case and must exactly match the workflow `steps[].operator` value.

#### 2. Implement BaseOperator

Custom operators inherit from `synthesis_engine.operators.base.BaseOperator`. The core interface is:

```python
from synthesis_engine.models import GenerationItem
from synthesis_engine.operators.base import BaseOperator


class MySynthesisOperator(BaseOperator):
    operator_name = "my_synthesis_operator"
    operator_version = "1.0.0"

    def process(self, item: GenerationItem) -> GenerationItem:
        item.generated["items"] = [{"instruction": item.prompt, "input": "", "output": "ok"}]
        item.metrics["custom_score"] = 1.0
        item.action = "accepted"
        return item
```

The executor passes step `params` into `self.config` and calls `setup()`, `process()`, and `teardown()` in order. `process()` reads `item.prompt` and `item.payload`, writes results into `item.generated`, writes quality, count, or debug data into `item.metrics`, appends issues into `item.issues`, and may set `item.action` to `accepted`, `filtered`, `failed`, or `needs_retry`.

#### 3. Follow Output Contracts by Task Type

| Operator type | Suggested input | Suggested output |
| --- | --- | --- |
| Text operator | Read `item.prompt`, `item.payload.topic`, `content`, `question`, `table`, and similar fields | Write `item.generated["items"]` or `instruction/input/output/text`, and add text quality metrics |
| Image operator | Read `item.prompt`, `payload.image_path`, `payload.image_paths`, or image-generation parameters | Write `item.generated["image_path"]`, `image_prompt`, `negative_prompt`, and confirm local files exist |
| Structured operator | Read `payload.schema`, field constraints, distribution parameters, or sample records | Write `item.generated["records"]` or `record`, and store field coverage or distribution metrics |
| Quality-gate operator | Read `item.generated`, `item.metrics`, `item.issues`, and `lineage.retry_attempt` | Set `item.action`; use `needs_retry` for retry and `filtered` for final rejected samples |

Do not remove core fields such as `id`, `task_type`, `prompt`, `payload`, `generated`, `metrics`, `issues`, `action`, or `lineage`. If a step uses resources that are not concurrency-safe, set `concurrent: false` in that step's `params`.

#### 4. Wire the Operator into a Workflow

```yaml
workflow:
  id: custom_text_synthesis
  retry_limit: 1

input:
  type: seed_yaml
  path: example_data/text/custom_text_seed.yaml

output:
  type: jsonl
  path: runs/custom_text_synthesis

custom_operators:
  - ./plugins/my_synthesis_operator.py

steps:
  - id: custom_generate
    operator: my_synthesis_operator
    params:
      threshold: 0.8
  - id: quality_gate
    operator: my_synthesis_operator
    params:
      pass_score: 0.7
      retry_limit: 1
```

`validate` loads `custom_operators` and tries to instantiate every `steps[].operator`, so it is the minimum pre-run check:

```bash
uv run synthesis validate -c workflows/custom_text_synthesis.yaml
uv run synthesis run -c workflows/custom_text_synthesis.yaml
uv run synthesis report -t runs/custom_text_synthesis
uv run synthesis trace -t runs/custom_text_synthesis --sample-id smoke_text_001
```

The workflow is ready when the minimal seed runs end to end, `generated.jsonl` contains accepted samples, `metrics.json` contains custom metrics, `report.md` is readable, and failed samples go to `filtered.jsonl` with explainable `issues`.

### Testing

```bash
uv run pytest
```

Current tests cover:

- workflow configuration loading and built-in operator creation;
- built-in prompt-library loading, custom prompt-directory override, and missing-template failures;
- text, image, structured, and mapper-layer workflows;
- flexible input adaptation for raw text, JSON, CSV, and related formats;
- custom operator loading and `operator-template`;
- resume, concurrency, and retry behavior.

You can also run lightweight documentation checks first:

```bash
uv run synthesis --help
uv run synthesis validate -c workflows/structured_synthesis.yaml
rg "synthesis (validate|run|report|trace|operator-template)" README_zh.md README.md
```

### Copyright and License

- This project is licensed under the MIT License. See [LICENSE](LICENSE).
