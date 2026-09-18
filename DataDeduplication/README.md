<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataDeduplication</h1>

<p align="center">
  <strong>DataReady · Intelligent Data Deduplication</strong><br>
  Usage Guide · Find duplicate samples and keep representative data.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-dedup-0284c7.svg" alt="CLI: dedup">
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
- [Input And Output](#dr-input-and-output)
- [Platform Users Run Deduplication Workflows](#dr-platform-users-run-deduplication-workflows)
- [Path Authorization](#dr-path-authorization)
- [Notes](#dr-notes)
- [Copyright and License](#dr-copyright-and-license)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

DataDeduplication is a workflow engine for deduplicating text, image, and audio samples. The Python package is named `dedup-workflow-engine`, the command-line entry point is `dedup`, and YAML workflows run end-to-end deduplication capabilities. Normalization, candidate recall, similarity fusion, duplicate clustering, representative selection, and report generation run inside the end-to-end operators.

The project publicly exposes three end-to-end operators: `text_dedup`, `image_dedup`, and `audio_dedup`. Local rules, feature computation, embedding, rerank, and ASR stages remain internal and are no longer directly referenced as built-in workflow operators.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `dedup` | [`text_dedup.yaml`](workflows/text_dedup.yaml) | Text · Image · Audio |

<a id="dr-features"></a>

## Core Capabilities

- **End-to-end text deduplication**: `text_dedup` runs text normalization, exact hashing, SimHash, MinHash LSH, optional embedding, optional rerank, edge fusion, clustering, and representative selection internally.
- **End-to-end image deduplication**: `image_dedup` runs image path resolution, file hashing, perceptual hashing, structural similarity, optional image embedding, optional object-region similarity, fusion, clustering, and representative selection internally.
- **End-to-end audio deduplication**: `audio_dedup` runs audio path resolution, file hashing, PCM hashing, energy fingerprinting, acoustic-feature similarity, optional audio embedding, optional ASR, fusion, clustering, and representative selection internally.
- **Workflow execution**: main workflows use one end-to-end operator step.
- **Auto routing**: `auto-run` reads mixed JSONL input, buckets samples by `text`, `image`, and `audio`, then runs matching workflows.
- **Traceable outputs**: each run writes kept samples, removed samples, review samples, duplicate groups, metrics, operator logs, Markdown report, and checkpoints.
- **Custom operators**: external Python operator files can be loaded through `custom_operators`, and `operator-template` can generate a starter template.
- **Output inspection**: duplicate groups and item decisions can be inspected by group ID or sample ID.

<a id="dr-installation"></a>

## Installation And Environment

### Requirements

- Python >= 3.10
- Runtime dependencies: `PyYAML`, `Pillow` (image processing)
- `uv` is recommended for command execution; this repository includes `uv.lock`

### Local Setup

```bash
cd DataDeduplication
uv sync
```

`uv sync` installs all runtime dependencies, including `Pillow` for image processing.

### Direct Command Invocation

If `dedup` is installed on the system `PATH`, invoke it directly:

```bash
dedup --help
```

If Windows PowerShell does not recognize `dedup`, activate the project virtual environment before invoking it:

```powershell
.\.venv\Scripts\Activate.ps1
dedup --help
```

### External Model Environment Variables

Default example workflows can run without external services. To enable embedding, rerank, ASR, or custom JSON services, use `configs/api_env.template.ps1` and `configs/model_registry.yaml` as references:

```powershell
$env:TEXT_RERANK_API_BASE = "https://coding.dashscope.aliyuncs.com/v1"
$env:TEXT_RERANK_MODEL = "qwen3.6-plus"
$env:TEXT_RERANK_API_KEY = "<put-your-api-key-in-current-shell-only>"
```

On startup, the command-line tries to load `configs/api_env.local.ps1` from the current directory. Do not commit real keys in that local file.

<a id="dr-quick-start"></a>

## Quick Start

### 1. Validate A Workflow Config

```bash
uv run dedup validate -c workflows/text_dedup_strict.yaml
```

Successful output:

```text
workflow config is valid
```

### 2. Run A Text Deduplication Workflow

```bash
uv run dedup run -c workflows/text_dedup_strict.yaml
```

The run writes outputs under `runs/text_strict/`. Public example workflows read the small redistributable samples under `example_data/` for environment checks and feature demos.

### 3. View The Run Report

```bash
sed -n '1,80p' runs/text_strict/report.md
```

The report includes workflow ID, sample counts, duplicate-edge count, removal rate, elapsed time, issue distribution, duplicate-group preview, and output-file notes.

### 4. Inspect A Duplicate Group Or Item

```bash
uv run dedup inspect-group --group-id dup_group_000001 --run-dir runs/text_strict
uv run dedup inspect-item --item-id txt_001 --run-dir runs/text_strict --input example_data/text/input.jsonl
```

<a id="dr-cli"></a>

## Command-Line Usage

Top-level help:

```bash
uv run dedup --help
```

Supported subcommands:

| Command | Purpose |
| --- | --- |
| `dedup run -c CONFIG [--resume]` | Run one YAML workflow config. |
| `dedup auto-run --input INPUT --output-dir OUTPUT_DIR [--workflow-dir workflows] [--profile strict|basic] [--modality auto|text|image|audio] [--resume]` | Read mixed JSONL, route by modality, and run matching workflows. |
| `dedup validate -c CONFIG` | Validate required workflow fields, input config, and end-to-end operator creation. |
| `dedup operator-template --type text|image|audio --name NAME --output OUTPUT` | Generate a loadable custom end-to-end operator template. |
| `dedup inspect-group --group-id GROUP_ID [--run-dir RUN_DIR]` | Print a duplicate group as JSON; without `run_dir`, searches `runs/*/duplicate_groups.jsonl` newest first. |
| `dedup inspect-item --item-id ITEM_ID --run-dir RUN_DIR [--input INPUT] [--max-text-chars N] [--verbose]` | Inspect sample input, output action, and related duplicate groups. |

The same entry point can be run as a module:

```bash
uv run python -m dedup_workflow_engine.cli.main validate -c workflows/text_dedup_strict.yaml
uv run python -m dedup_workflow_engine run -c workflows/text_dedup_strict.yaml
```

<a id="dr-input-and-output"></a>

## Input And Output

### Input Format

The standard input item schema is in `src/dedup_workflow_engine/schemas/input_schema.json`. Each sample requires at least:

```json
{
  "id": "sample_001",
  "modality": "text",
  "payload": {
    "text": "text to deduplicate"
  },
  "meta": {}
}
```

Supported `modality` values are `text`, `image`, and `audio`. Common payload fields:

| Modality | Payload field |
| --- | --- |
| `text` | `text` |
| `image` | `image_path` |
| `audio` | `audio_path` |

Workflow input configs also support `auto`, `jsonl`, `json`, `csv`, `directory`, `file`, `stdin`, and `raw_text`, plus field mapping through `id_field`, `modality_field`, `text_field`, `image_path_field`, and `audio_path_field`.

Built-in public sample inputs:

- `example_data/text/input.jsonl`
- `example_data/image/input.jsonl`
- `example_data/audio/input.jsonl`

### Workflow Config

The workflow schema is in `src/dedup_workflow_engine/schemas/workflow_schema.json`. A workflow requires `workflow`, `input`, `output`, and `steps`:

```yaml
workflow:
  id: text_dedup_strict_v1
  name: Strict text deduplication workflow
  modality: text
  mode: pipeline
  checkpoint: true

input:
  type: jsonl
  path: ./example_data/text/input.jsonl

output:
  run_dir: ./runs/text_strict

steps:
  - id: text_dedup
    operator: text_dedup
    params:
      profile: strict
      methods:
        exact_hash: true
        simhash:
          bit_size: 64
          ngram: 2
          max_hamming_distance: 10
        minhash:
          shingle_size: 5
          min_length: 35
          jaccard_threshold: 0.55
        embedding: false
        rerank: false
      thresholds:
        cluster_min_score: 0.55
```

Built-in workflows live under `workflows/` and include basic and strict text/image/audio workflows. The public delivery path uses the workflows that read from `example_data/`.

### Output Files

The standard output item schema is in `src/dedup_workflow_engine/schemas/output_schema.json`. Each final sample requires `id`, `modality`, and `action`, where `action` is `keep`, `remove`, or `review`.

Each run directory usually contains:

| File | Description |
| --- | --- |
| `kept.jsonl` | Final retained samples. |
| `removed.jsonl` | Samples removed because another representative was selected. |
| `review.jsonl` | Samples requiring manual review. |
| `duplicate_groups.jsonl` | Duplicate clusters, members, keep/remove decisions, reasons, and scores. |
| `metrics.json` | Workflow-level metrics, elapsed time, throughput, checkpoint state, and processed counts. |
| `operator_logs.jsonl` | Operator-level execution logs. |
| `report.md` | Markdown summary report. |
| `checkpoints/` | Step snapshots when checkpointing is enabled. |

<a id="dr-platform-users-run-deduplication-workflows"></a>

## Platform Users Run Deduplication Workflows

The user path is "prepare input -> validate config -> run -> inspect output":

```bash
uv run dedup validate -c workflows/text_dedup_strict.yaml
uv run dedup run -c workflows/text_dedup_strict.yaml
uv run dedup inspect-group --group-id dup_group_000001 --run-dir runs/text_strict
uv run dedup inspect-item --item-id txt_001 --run-dir runs/text_strict --input example_data/text/input.jsonl
```

Mixed-modality input uses `auto-run`. The platform detects `text`, `image`, and `audio` from `modality` or from `payload.text`, `payload.image_path`, and `payload.audio_path`, then selects workflows by profile:

```bash
uv run dedup auto-run --input data/mixed/input.jsonl --output-dir runs/mixed_auto --workflow-dir workflows --profile strict
```

`auto-run --profile basic` looks for `workflows/{modality}_dedup.yaml`, while `strict` looks for `workflows/{modality}_dedup_strict.yaml`. For a clean rerun, use a new `output.run_dir` or clear the target run directory; `--resume` enables checkpointing and tries to reuse successful steps.

<a id="dr-path-authorization"></a>

## Path Authorization

`scripts/build_manifest.py` accesses input and output paths under the current working directory by default. Use the repeatable `--allow-root <directory>` option to authorize another existing directory. Command-line path options are converted to standard path objects during argument parsing, then canonicalized and checked against the authorized roots. Every canonical path must remain under the current working directory or an authorized directory. Every discovered file is checked again by its canonical path, so a symlink or junction that points outside the authorized roots is rejected.

```bash
uv run python scripts/build_manifest.py --text-dir D:/datasets/texts --output data/input.jsonl --allow-root D:/datasets
```

<a id="dr-notes"></a>

## Notes

- Do not write or commit real API keys in the repository; prefer current-shell environment variables or local `configs/api_env.local.ps1`.
- External embedding, rerank, and ASR internal stages in strict workflows are usually configured with `enabled: false`; verify service URL, model name, key, and input field before enabling them.
- Image workflows read `image_path`, and audio workflows read `audio_path`; relative paths are resolved by the run directory and input adapter logic, so run examples from the project root.
- `--resume` enables checkpointing and tries to reuse existing outputs; for a clean rerun, use a new `output.run_dir` or clear the target run directory.
- `auto-run --profile basic` looks for `workflows/{modality}_dedup.yaml`, while `strict` looks for `workflows/{modality}_dedup_strict.yaml`.
- Custom end-to-end operators should inherit from `dedup_workflow_engine.operators.base.BaseOperator`, define a unique `operator_name`, and be listed under `custom_operators` in the workflow.

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
