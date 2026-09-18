<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">MultimodalParsing</h1>

<p align="center">
  <strong>DataReady · Multimodal Content Parsing</strong><br>
  Development Guide · Turn documents, images, and audio into structured content.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-parse-0284c7.svg" alt="CLI: parse">
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
- [OCRFlux Response Validation](#dr-ocrflux-response-validation)
- [Validation and Testing](#dr-testing)
- [Related Documentation](#dr-documentation)

</details>

<a id="dr-overview"></a>

## Overview

MultimodalParsing is a lightweight multimodal content parsing workflow engine. It uses YAML workflow files to orchestrate input adaptation, end-to-end parsing operators, and run reports. Markdown reconstruction, chunking, quality assessment, and other intermediate stages run inside the end-to-end operators. It is designed to convert PDF, Word, Excel, HTML, image, audio, and structured text inputs into unified JSONL parsing artifacts.

| Command | Example workflow | Data types |
| --- | --- | --- |
| `parse` | [`pdf_parse.yaml`](workflows/pdf_parse.yaml) | PDF · Word · Excel · HTML · Image · Audio |

<a id="dr-project-structure"></a>

## Project Structure

```text
MultimodalParsing/
├── pyproject.toml                 # Package metadata, dependencies, and parse command-line entry point
├── example_data/                  # Public example data for general users
├── docs/                          # Documentation directory: acceptance criteria, workflow guide, operator inventory, and related materials
├── src/parse_engine/
│   ├── cli/main.py                # Click command-line: validate/run/operator-template/report/trace
│   ├── models.py                  # DataItem, Artifact, SourceTrace
│   ├── schemas/                   # Input, output, and workflow JSON Schema files
│   ├── runtime/                   # Config, input adapter, executor, registry, report, checkpoint
│   ├── utilities/                 # Pure utilities and orchestration helpers
│   │   ├── document/              # Document parsing service clients
│   │   ├── markdown/              # Markdown chunker, rebuilder, and chunk artifact helpers
│   │   └── pipeline.py            # Shared pipeline orchestration helpers
│   └── operators/                 # End-to-end parsing operators
│       ├── common/                # Shared internal capabilities across formats
│       │   ├── markdown/          # Markdown workflow-stage boundary with thin operator wrappers
│       │   └── parse_quality.py   # Parsing quality assessment
│       ├── pdf_parse/             # PDF operator, pipeline, and document extraction logic
│       ├── word_parse/            # Word operator, pipeline, and document structure extraction logic
│       ├── excel_parse/           # Excel operator, pipeline, and table structure extraction logic
│       ├── html_parse/            # HTML operator, pipeline, and body extraction logic
│       ├── image_parse/           # Image operator, pipeline, metadata, and OCR logic
│       └── audio_parse/           # Audio operator, pipeline, metadata, and ASR logic
│           └── asr/               # ASR backend/factory/result adapters
├── tests/                         # pytest unit tests and workflow regression tests
└── workflows/                     # Example and validation workflow YAML files
```

<a id="dr-custom-operators"></a>

## Developing Custom Operators

### Run a Workflow

Prepare input data and a workflow YAML file, then use the fixed entrypoints to validate, run, and inspect results:

```bash
uv run parse validate -c workflows/pdf_parse.yaml
uv run parse run -c workflows/pdf_parse.yaml
uv run parse report -t runs/pdf_parse
uv run parse trace --sample-id html40 -t runs/pdf_parse
```

Workflow `steps[].operator` references an already registered end-to-end operator name. Built-in end-to-end operators are registered automatically when the command-line starts. External operators must be declared in the same workflow through `custom_operators`.

### Development Workflow

Provide a loadable end-to-end Python operator file and a minimal workflow sample. A recommended plugin location is `workflows/plugins/`, so `custom_operators` can use one stable relative-path convention.

1. Generate a template:

```bash
mkdir -p workflows/plugins
uv run parse operator-template \
  --type text \
  --name my_parse_operator \
  --output workflows/plugins/my_parse_operator.py
```

2. In the template, inherit from `BaseOperator`, keep `operator_name` in snake_case, and implement `process(self, item)`:

```python
from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.base import BaseOperator


class MyParseOperatorOperator(BaseOperator):
    operator_name = "my_parse_operator"
    operator_version = "1.0.0"

    def process(self, item: DataItem) -> DataItem:
        text = str(item.payload.get("text", ""))
        item.artifacts.append(
            Artifact(
                id=f"{item.id}_custom_text",
                type="text",
                text=text.strip(),
                data={"source": "custom"},
                source_trace=SourceTrace(
                    file=item.source.get("path", item.id),
                    operator=self.operator_name,
                ),
            )
        )
        item.metrics["custom_artifact_count"] = len(item.artifacts)
        item.action = "parsed"
        return item
```

`BaseOperator` receives the workflow step `params` and stores them in `self.config`. Override `setup()` and `teardown()` when the operator needs to load models, open resources, or release resources. The default `process_batch()` calls `process()` item by item.

3. Wire it into a workflow:

```yaml
workflow:
  id: custom_parse
input:
  type: raw_text
  text: parse a piece of text
output:
  type: jsonl
  path: runs/custom_parse
custom_operators:
  - ./plugins/my_parse_operator.py
steps:
  - id: custom
    operator: my_parse_operator
    params:
      threshold: 0.8
```

`custom_operators` accepts Python file paths or importable module names. Relative custom operator paths are resolved against the workflow YAML directory. Relative `input.path` and `output.path` values are resolved against the project directory one level above the workflow file directory. `steps[].operator` must match the class `operator_name`; otherwise `parse validate` reports an unknown operator.

### Output and Acceptance Contract

Custom operators should write structured parsing results to `item.artifacts`, counts, scores, timing, or similar statistics to `item.metrics`, diagnostics to `item.issues`, and the final state to `item.action`. After execution, the workflow writes:

| Output | Source |
| --- | --- |
| `artifacts.jsonl` | Each `DataItem` with its `artifacts`, `metrics`, `issues`, and `action`. |
| `failed.jsonl` | Samples whose `action == "failed"`. |
| `metrics.json` | Totals, modality distribution, artifact types, issue types, concurrency, and resume metrics. |
| `report.md` | Markdown report generated from the current run results. |

Before publishing changes, run at least one minimal sample validation:

```bash
uv run parse validate -c workflows/custom_parse.yaml
output_dir=$(uv run parse run -c workflows/custom_parse.yaml)
uv run parse report -t "$output_dir"
sample_id=$(python -c 'import json,sys; print(json.loads(open(sys.argv[1], encoding="utf-8").readline())["id"])' "$output_dir/artifacts.jsonl")
uv run parse trace --sample-id "$sample_id" -t "$output_dir"
```

For `raw_text` input, the input adapter generates the sample id. For file, JSONL, CSV, and other inputs, the id can also come from file names or mapped fields. Validation should use the actual generated `DataItem.id`; you can also trace a single artifact by using its artifact id.

<a id="dr-ocrflux-response-validation"></a>

## OCRFlux Response Validation

OCRFlux cross-page element merging accepts only a list of integer index pairs. Responses are parsed with the Python standard-library `ast.literal_eval` and validated for shape and index bounds before entering the page-merge flow; response content is never executed as a Python expression.

<a id="dr-testing"></a>

## Validation and Testing

Run the full test suite:

```bash
uv run pytest
```

Run focused regression tests:

```bash
uv run pytest tests/test_config.py tests/test_flexible_input_custom_operator.py
uv run pytest tests/test_pdf_operator.py tests/test_word_workflow.py tests/test_excel_workflow.py
uv run pytest tests/test_html_operator.py
uv run pytest -q
```

Tests cover workflow configuration loading, end-to-end operator registration, PDF/Word/Excel/HTML parsing, internal Markdown chunking, the internal audio ASR stage, flexible input adaptation, custom end-to-end operator loading, and the command-line `operator-template` and `validate` behavior.

<a id="dr-documentation"></a>

## Related Documentation

- [Usage guide](README.md) · [Development guide](README_dev.md)
- [Workflow configuration (Chinese)](docs/Workflow配置说明.md) · [Example workflows](workflows/)
- [Example data sources](example_data/SOURCES_en.md) · [Third-party licenses (Chinese)](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">Back to top</a> &nbsp;·&nbsp; <a href="../README.md">DataReady home</a>
</p>
