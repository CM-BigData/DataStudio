# DataStudio-HighQualityDataSynthesis

> 中文版本: [README_dev_zh.md](README_dev_zh.md)

DataStudio-HighQualityDataSynthesis is a lightweight workflow engine for high-quality data synthesis tasks. It uses YAML workflows to orchestrate input adaptation, text/image/structured data synthesis, end-to-end synthesis operators, internal quality loops, retry, resume, and report generation. After installation, it exposes the `synthesis` command-line entry point.


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

### Model Endpoint Security

The OpenAI-compatible client validates endpoints during configuration parsing and again when constructing the SDK client. Remote endpoints carrying API keys must use HTTPS; HTTP is accepted only for `localhost`, `127.0.0.1`, or `::1`. Public workflows reference environment variables through `api_base_env` and `api_key_env` instead of embedding remote service addresses or credentials.

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
