<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataDeduplication</h1>

<p align="center">
  <strong>DataReady · Intelligent Data Deduplication</strong><br>
  Development Guide · Find duplicate samples and keep representative data.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-dedup-0284c7.svg" alt="CLI: dedup">
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
- [Developing Custom Operators](#dr-custom-operators)
- [Development Workflow](#dr-development-workflow)
- [Platform Integration Contract](#dr-platform-integration-contract)
- [Integration And Troubleshooting Flow](#dr-integration-and-troubleshooting-flow)
- [Testing](#dr-testing)
- [Helper Script](#dr-helper-script)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

DataDeduplication is a workflow engine for deduplicating text, image, and audio samples. The Python package is named `dedup-workflow-engine`, the command-line entry point is `dedup`, and YAML workflows run end-to-end deduplication capabilities. Normalization, candidate recall, similarity fusion, duplicate clustering, representative selection, and report generation run inside the end-to-end operators.

The project publicly exposes three end-to-end operators: `text_dedup`, `image_dedup`, and `audio_dedup`. Local rules, feature computation, embedding, rerank, and ASR stages remain internal and are no longer directly referenced as built-in workflow operators.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `dedup` | [`text_dedup.yaml`](workflows/text_dedup.yaml) | Text · Image · Audio |

<a id="dr-project-structure"></a>

## Project Structure

```text
DataDeduplication/
├── pyproject.toml                         # Package metadata, dependencies, and dedup entry point
├── configs/                               # Runtime and external model-service config templates
├── example_data/                          # Public small sample inputs and ground truth
├── docs/                                  # Documentation directory; the current delivery includes the workflow configuration guide
├── data/                                  # Internal validation and historical sample data
├── runs/                                  # Sample run outputs
├── src/dedup_workflow_engine/
│   ├── cli/                               # argparse command-line entry point
│   ├── operators/                         # End-to-end operator entry points, per-modality pipeline orchestration, and shared postprocess helpers
│   ├── utilities/                         # Pure utilities and shared algorithm helpers
│   ├── runtime/                           # Config loading, input adapter, registry, scheduler, executor, report
│   └── schemas/                           # Input, output, and workflow JSON Schemas
├── tests/                                 # Unit tests and command-line/workflow smoke tests
└── workflows/                             # Runnable YAML workflows
```

Main built-in end-to-end operator names can be used directly in `steps[].operator`:

- `text_dedup`
- `image_dedup`
- `audio_dedup`

The built-in modality directory convention is:

- `text_dedup/operator.py` keeps the workflow-facing entry class, while `text_dedup/pipeline.py` owns text end-to-end orchestration.
- `image_dedup/operator.py` keeps the workflow-facing entry class, while `image_dedup/pipeline.py` owns image end-to-end orchestration.
- `audio_dedup/operator.py` keeps the workflow-facing entry class, while `audio_dedup/pipeline.py` owns audio end-to-end orchestration.
- `operators/common/` is reserved for cross-modality reusable helpers and postprocess stages, not modality-specific end-to-end orchestration.

<a id="dr-custom-operators"></a>

## Developing Custom Operators

This section is for developers who extend deduplication behavior on top of the platform. Platform users normally prepare an input JSONL file or directory, choose a workflow under `workflows/`, then run `validate`, `run`, or `auto-run`; developers deliver workflow-loadable end-to-end operators together with minimal samples and verifiable configuration.

<a id="dr-development-workflow"></a>

## Development Workflow

A custom end-to-end operator must inherit from `dedup_workflow_engine.operators.base.BaseOperator`, define a unique snake_case `operator_name`, and be listed in workflow-level `custom_operators`. Prefer putting external platform plugins under `workflows/plugins/`, such as `workflows/plugins/my_text_dedup.py`, instead of mixing them into built-in `src/dedup_workflow_engine/operators/`.

Generate a starting template:

```bash
mkdir -p workflows/plugins
uv run dedup operator-template --type text --name my_text_dedup --output workflows/plugins/my_text_dedup.py
```

Supported template types are `text`, `image`, and `audio`. The generated file includes `BaseOperator`, `operator_name`, the `process_dataset` input/output contract, and a workflow example; normalization, recall, fusion, clustering, and selection logic should be encapsulated inside one end-to-end operator.

Minimal loadable workflow example:

```yaml
workflow:
  id: custom_text_dedup
  modality: text
input:
  type: raw_text
  text: demo
output:
  run_dir: ./runs/custom_text
custom_operators:
  - ./plugins/my_text_dedup.py
steps:
  - id: my_text_dedup
    operator: my_text_dedup
    params:
      profile: basic
      threshold: 0.9
```

`steps[].operator` must match the end-to-end operator class's `operator_name`. `steps[].params` is passed to the operator as `self.config`, so use it for `profile`, `methods`, `thresholds`, `model_ref`, and similar end-to-end settings. `validate` loads `custom_operators` and instantiates every step, which catches missing files, misspelled `operator_name`, duplicate registration, missing input paths, and unknown `input.type` before a run.

<a id="dr-platform-integration-contract"></a>

## Platform Integration Contract

- Path resolution: in `dedup run -c path/to/workflow.yaml`, relative `custom_operators` paths are resolved from the workflow file directory; if plugins live under `workflows/plugins/`, the workflow should use `./plugins/<name>.py`. `input.path`, `output.run_dir`, and relative sample `image_path` or `audio_path` values are resolved from the current command working directory. Run commands from the project root or use absolute paths in config.
- Input fields: a standard sample contains `id`, `modality`, `payload`, and `meta`; text reads `payload.text`, image reads `payload.image_path`, and audio reads `payload.audio_path`. The input adapter also supports `id_field`, `modality_field`, `text_field`, `image_path_field`, and `audio_path_field` for CSV/JSON mapping.
- Output fields: end-to-end operators must not remove `id`, `modality`, `payload`, `meta`, `intermediate`, `metrics`, `issues`, or `action`. Internal temporary results may go to `intermediate`, debug or quality scores to `metrics`, explainable problems to `issues`, and duplicate candidate edges to `context["duplicate_edges"]`.
- External services: embedding, rerank, ASR, and custom JSON services can stay disabled by default. Before enabling one, configure switches under the end-to-end step's `params.methods` or `params.model_ref`, and set the matching `*_API_BASE`, `*_API_KEY`, and `*_MODEL` in the current shell or `configs/api_env.local.ps1`.
- Minimal sample validation: before delivery, provide at least 2 to 5 JSONL or `raw_text` samples that trigger the target logic, run `uv run dedup validate -c <workflow>`, then `uv run dedup run -c <workflow>`, and finally use `inspect-group`, `inspect-item`, and `operator_logs.jsonl` to prove the end-to-end operator ran and produced expected output.

<a id="dr-integration-and-troubleshooting-flow"></a>

## Integration And Troubleshooting Flow

1. Generate a template and confirm the name: `operator-template --name my_operator` accepts snake_case only, and the workflow uses `operator: my_operator`.
2. Add the file to `custom_operators`: relative paths are based on the workflow file directory; a missing file fails `validate` with `Custom operator file not found`.
3. Validate the workflow: `uv run dedup validate -c <workflow>`; if you see `Unknown operator`, check `operator_name`, `steps[].operator`, and whether `custom_operators` is declared.
4. Run minimal samples: validate a single end-to-end operator first with `raw_text`, a small JSONL file, or 2 to 5 media files, then integrate it into the full strict workflow.
5. Inspect results: check `runs/<name>/operator_logs.jsonl` for `step_id`, `operator`, and `status`; use `inspect-group` for duplicate clusters, and `inspect-item --verbose` for one item's `intermediate`, `metrics`, `issues`, and final `action`.
6. Fix external-service issues: when a service is enabled but environment variables are missing or the service fails, samples may contain issues such as `text_embedding_api_not_configured`, `text_rerank_api_not_configured`, `image_embedding_api_failed`, `audio_embedding_api_failed`, `asr_api_not_configured`, or `asr_api_failed`; first check `enabled`, environment variables, endpoint, model name, key, and response fields.

<a id="dr-testing"></a>

## Testing

Run all tests:

```bash
uv run pytest
```

Test coverage by area:

- `tests/test_runtime.py`: workflow execution, output files, metrics, and reports.
- `tests/test_text_rules.py`: internal text normalization, exact hashing, SimHash, and MinHash helper functions.
- `tests/test_parallel_executor.py`: parallel DAG levels and checkpoints.
- `tests/test_router.py`: modality detection and auto routing.
- `tests/test_flexible_input_custom_operator.py`: flexible input, CSV/JSON/raw text, custom operators, and template generation.
- `tests/test_build_manifest.py`: directory scanning and manifest generation.
- `tests/test_env_loader.py`: local PowerShell environment loading.
- `tests/test_rerank_edges.py`: rerank candidate-edge deduplication and merging.

<a id="dr-helper-script"></a>

## Helper Script

- `scripts/build_manifest.py`: scans directories such as `texts`, `images`, and `audios`, then generates a unified `input.jsonl` for `dedup auto-run` or other workflows.
- `--text-dir` accepts both raw text files (`.txt/.md`) and structured text manifests (`.jsonl/.json/.csv`); structured records read `payload.text` first, then `text`, `content`, or `body`, and skip records without usable text.
- Example:

```bash
uv run python scripts/build_manifest.py \
  --text-dir data/texts \
  --image-dir data/images \
  --audio-dir data/audios \
  --output data/input.jsonl
```

The script converts input directories, the output file, `--relative-base`, and `--allow-root` to standard path objects during argument parsing. It then applies canonical containment to those paths and every file discovered during directory traversal. The current working directory is authorized by default; repeat `--allow-root <directory>` to authorize another existing directory. A symlink or junction that resolves outside the authorized roots is rejected.

<a id="dr-documentation"></a>

## Related Documentation

- [Usage guide](README.md) · [Development guide](README_dev.md)
- [Workflow configuration (Chinese)](docs/Workflow配置说明.md) · [Example workflows](workflows/)
- [Example data sources](example_data/SOURCES_en.md) · [Third-party licenses (Chinese)](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">Back to top</a> &nbsp;·&nbsp; <a href="../README.md">DataReady home</a>
</p>
