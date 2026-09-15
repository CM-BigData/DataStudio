# DataStudio-HighQualityDataSynthesis

> English version: [README.md](README.md)

DataStudio-HighQualityDataSynthesis 是一个面向高质量数据合成任务的轻量级工作流引擎。项目通过 YAML workflow 编排输入适配、文本/图像/结构化数据合成、端到端合成算子、内部质量闭环、重试、断点续跑和报告输出，安装后提供 `synthesis` 命令行入口。

## 部署使用手册

### 核心能力

- **工作流驱动**：通过 `workflows/*.yaml` 声明 `workflow`、`input`、`output`、`steps` 和可选 `custom_operators`。
- **多类型输入**：支持 `seed_yaml`、`jsonl`、`json`、`csv`、`directory`、`file`、`stdin`、`raw_text`，也支持 `auto` 自动识别常见文件类型。
- **内置合成算子**：覆盖文本合成、图像模型合成、结构化记录合成、文本 QA、表格 QA、同义词替换、问题增强和多模态合成等场景。
- **质量闭环**：校验、多样性、安全过滤和质量门控作为端到端算子的内部阶段执行，不作为公开 workflow 算子暴露。
- **工具目录边界**：`src/synthesis_engine/utilities/` 只放纯工具/helper，例如多样性签名、结构化分布/记录/校验辅助函数、图像负向提示词与质量校验辅助函数；文本 mapper 重试管线这类业务编排入口保留在 `src/synthesis_engine/operators/text_synthesis/pipeline.py`，`operators/common/` 仅保留仍具工作流公共能力的过滤算子。
- **运行可追踪**：每次运行在 `output.path` 写入 workflow 副本、JSONL 输出、指标、报告和 checkpoint，便于多个工具串行衔接。
- **自定义扩展**：可用 `synthesis operator-template` 生成自定义算子模板，并在 workflow 的 `custom_operators` 中加载。

### 安装与环境

#### 环境要求

- Python >= 3.10
- 推荐使用 `uv`
- 运行依赖来自 `pyproject.toml`：`click`、`openai`、`PyYAML`、`Pillow`、`tenacity`、`httpx[socks]`
- 开发测试依赖：`pytest`

#### 本地安装

```bash
cd DataStudio-HighQualityDataSynthesis
uv sync
uv run synthesis --help
```

#### 直接调用命令

如果 `synthesis` 已安装到系统 `PATH`，可直接调用：

```bash
synthesis --help
```

Windows PowerShell 中如未识别 `synthesis`，可先激活项目虚拟环境后再调用：

```powershell
.\.venv\Scripts\Activate.ps1
synthesis --help
```

文本 LLM workflow 通过官方 `openai` SDK 调用 OpenAI-compatible 服务，并从 `model_config` 或 `configs/model_registry.yaml` 读取配置。常用环境变量包括：

```bash
export LLM_API_BASE=<openai-compatible-base-url>
export LLM_API_KEY=<api-key>
```

携带 API 密钥访问远程 OpenAI-compatible 服务时，`LLM_API_BASE` 必须使用 HTTPS。HTTP 仅用于 `localhost`、`127.0.0.1` 或 `::1` 上的本地兼容服务。图像合成和问题增强示例从 `LLM_API_BASE` 读取端点，并从 `OPENAI_API_KEY` 读取密钥。

结构化记录、模板文本、同义词替换等 workflow 可在不配置外部 LLM 的情况下运行；`text_llm_synthesis`、图像合成、多模态合成和问题增强等真实模型 workflow 需要有效模型配置。

### 快速开始

#### 1. 校验 workflow

```bash
uv run synthesis validate -c workflows/structured_synthesis.yaml
```

成功时输出类似：

```text
OK: structured_synthesis_v1 (7 steps)
```

#### 2. 运行 workflow

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml
```

命令会输出本次输出目录，例如：

```text
/path/to/DataStudio-HighQualityDataSynthesis/runs/structured_synthesis
```

#### 3. 查看报告

```bash
uv run synthesis report -t runs/structured_synthesis
```

`report` 直接读取 `output.path` 下的 `report.md`。

#### 4. 追踪样本

```bash
uv run synthesis trace -t runs/structured_synthesis --sample-id record_dataset_source
```

`trace` 会在 `generated.jsonl` 和 `filtered.jsonl` 中查找样本并输出格式化 JSON。

### 命令行用法

安装后只有一个脚本入口：`synthesis = synthesis_engine.cli.main:cli`。

```bash
synthesis [OPTIONS] COMMAND [ARGS]...
```

| 命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `validate` | 校验 workflow 配置、输入路径和算子可创建性 | `-c, --config PATH` |
| `run` | 执行 workflow 并输出输出目录 | `-c, --config PATH`、`--resume` |
| `operator-template` | 生成自定义算子模板 | `--type text\|image\|structured\|quality_gate`、`--name`、`--output` |
| `report` | 打印输出目录下的 `report.md` | `-t, --task PATH` |
| `trace` | 按样本 ID 查询生成或过滤结果 | `--sample-id TEXT`、`-t, --task PATH` |

#### 断点续跑

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml --resume
```

续跑时会从 `output.path` 读取已有 `generated.jsonl`，跳过已被标记为 `accepted` 的样本，并更新 checkpoint 和指标。

#### 生成自定义算子模板

```bash
mkdir -p workflows/plugins
uv run synthesis operator-template --type text --name my_synthesis_operator --output workflows/plugins/my_synthesis_operator.py
```

生成的 Python 文件可通过 workflow 加载：

```yaml
custom_operators:
  - ./plugins/my_synthesis_operator.py
steps:
  - id: custom
    operator: my_synthesis_operator
    params: {}
```

自定义算子的 `operator_name` 必须使用 snake_case。

### 运行数据生成 workflow

只需要准备 workflow、seed 和输出目录，不需要改 Python 代码。推荐把 workflow 放在 `workflows/`，把输入样本放在 `example_data/` 或本地数据目录，把运行产物写到 `output.path` 指定的目录。

#### 接入约定

| 配置 | 约定 |
| --- | --- |
| `workflow` | 声明 `id`、`name`、`batch_size`、`concurrency`、`checkpoint`、`retry_limit` 等运行元数据 |
| `input` | 声明 seed 来源；常用 `type: seed_yaml` + `path: example_data/**/*.yaml`，也可使用 JSONL、JSON、CSV、目录、文件、stdin 或 raw text |
| `output.path` | 运行输出目录；`run` 会直接写入该目录 |
| `steps[].operator` | 引用内置或自定义算子的 `operator_name`，执行顺序就是 YAML 中的 steps 顺序 |
| `custom_operators` | 可选；加载自定义 Python 文件或模块 |

最小 seed 建议只放 1 条样本，用于接入验证：

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

先校验配置和算子是否可创建：

```bash
uv run synthesis validate -c workflows/structured_synthesis.yaml
```

再运行 workflow：

```bash
uv run synthesis run -c workflows/structured_synthesis.yaml
```

运行完成后，读取输出目录中的产物：

| 文件 | 用途 |
| --- | --- |
| `generated.jsonl` | 生成数据，只包含 `action=accepted` 的样本 |
| `filtered.jsonl` | 审计数据，包含 `action=filtered` 或 `action=failed` 的样本 |
| `metrics.json` | 总量、任务类型、动作分布、质量分、并发和续跑统计 |
| `report.md` | 面向人工检查的汇总报告 |
| `workflow.yaml` | 本次运行使用的 workflow 副本 |
| `checkpoint.json` | 断点续跑状态 |

可用以下命令查看报告和追踪单条样本：

```bash
uv run synthesis report -t runs/structured_synthesis
uv run synthesis trace -t runs/structured_synthesis --sample-id record_dataset_source
```

#### 模型与凭据

文本 LLM 算子优先读取 step `params.model_config`，否则通过 `model_ref` 读取 `configs/model_registry.yaml`。当前示例使用 OpenAI-compatible 环境变量：

```bash
export LLM_API_BASE=<openai-compatible-base-url>
export LLM_API_KEY=<api-key>
```

远程 OpenAI-compatible 端点在携带 API 密钥时必须使用 HTTPS；本机回环地址可以使用 HTTP。`workflows/image_synthesis.yaml` 和 `workflows/text_question_augmentation.yaml` 使用 `LLM_API_BASE` 与 `OPENAI_API_KEY`。

结构化记录、模板文本和部分离线改写 workflow 不需要外部凭据。图像合成需要配置文生图模型。无凭据时，应先运行 `validate` 或选择 `workflows/structured_synthesis.yaml` 这类本地 workflow，并用最小 seed 验证 `generated.jsonl`、`metrics.json` 和 `report.md` 是否生成。

#### Prompt 模板库

当前 Prompt 模板库默认目录是 `src/synthesis_engine/prompts/`。每个模板文件使用 YAML，至少支持 `system` 与 `user` 两个顶层字段；也支持带 `metadata`、`messages`、`output_schema` 的结构化模板。模板内容里可以引用 `{{ seed_id }}`、`{{ prompt }}`、`{{ topic }}`、`{{ audience }}`、`{{ style }}`、`{{ question }}`、`{{ text }}` 等变量。

workflow 中可通过 step 参数覆盖默认模板目录或模板名：

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

最小模板示例：

```yaml
system: |
  You are a data synthesis model.
user: |
  Seed id: {{ seed_id }}
  Source prompt: {{ prompt }}
  Topic: {{ topic }}
```

当前边界说明：

- 未设置 `prompt_dir` 时，会自动读取内置 Prompt 库。
- `prompt_template` 不存在时，运行会以缺失模板文件的明确错误失败，便于尽早发现配置问题。
- 当前已接入模板库的文本能力包括 `text_llm_synthesis`、`question_decomposition`、`question_augmentation`、`text_rewrite`。
- `question_augmentation` 默认按 `language` 选择 `question_augmentation_en` 或 `question_augmentation_zh`，也可通过 `prompt_template` 显式覆盖。
- 多模态与图像生成相关 prompt 仍保留在对应实现中，后续若统一收口到 Prompt 库，可沿用同样的 YAML 模板约定。

### 输入与输出

#### Workflow 配置

最小 workflow 结构如下：

```yaml
workflow:
  id: structured_synthesis_v1
  name: 结构化数据合成流程
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

`workflow.concurrency` 会控制样本级并发；当算子未禁用并发且存在多个待处理样本时，执行器会用线程池处理样本并保留输入顺序。

#### 输入样本

`seed_yaml` 输入使用 `items` 列表：

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

归一化后的样本字段包括：

| 字段 | 说明 |
| --- | --- |
| `id` | 样本 ID；缺失时由行号、文件名或时间戳生成 |
| `task_type` | `text`、`image` 或 `structured` |
| `prompt` | 原始合成意图 |
| `payload` | 业务字段，例如 schema、topic、image path 等 |
| `lineage` | 输入来源、seed ID、重试历史等追踪信息 |

JSON、JSONL、CSV 可通过 `id_field`、`task_type_field`、`prompt_field` 显式映射字段；未映射的额外字段会进入 `payload`。

#### 输出文件

每次 `run` 会直接在 `output.path` 下写入：

| 文件 | 内容 |
| --- | --- |
| `workflow.yaml` | 本次运行使用的 workflow 副本 |
| `generated.jsonl` | `action=accepted` 的可发布样本 |
| `filtered.jsonl` | `action=filtered` 或 `action=failed` 的审计样本 |
| `metrics.json` | 总量、任务类型、动作、问题类型、平均质量分、多样性分、续跑和并发统计 |
| `report.md` | Markdown 汇总报告 |
| `checkpoint.json` | 运行状态、已完成样本、跳过数量等 checkpoint 信息 |

运行汇总遵循 `output.path/metrics.json` 输出，并在 `output.path/report.md` 中展示，核心字段包括：

- `input_total_count`：当前输入样本总数
- `total`：本次实际处理样本数
- `historical_completed_count`：当前输入中已由历史输出完成的样本数
- `newly_processed_count`：本次新增处理样本数
- `current_completed_count`：当前输入中已完成样本数
- `pending_count`：当前输入中仍未完成样本数

单条输出样本是 `GenerationItem` 的 JSON 表示，主要字段包括 `id`、`task_type`、`prompt`、`payload`、`generated`、`metrics`、`issues`、`action`、`lineage`。

### 内置 workflow 与算子

| 示例 workflow | 输入 | 主要用途 |
| --- | --- | --- |
| `workflows/text_synthesis.yaml` | `example_data/text/text_topics.yaml` | 调用 `text_llm_synthesis` 生成 instruction/input/output 文本样本 |
| `workflows/structured_synthesis.yaml` | `example_data/structured/structured_schema.yaml` | 按字段 schema 生成结构化记录并校验 |
| `workflows/image_synthesis.yaml` | `example_data/image/image_prompts.yaml` | 调用文生图模型生成 PNG 图片并校验尺寸 |
| `workflows/text_qa_synthesis.yaml` | `example_data/text/text_qa_sources.yaml` | 从文本源生成 QA 样本 |
| `workflows/text_synonym_replacement.yaml` | `example_data/text/synonym_replacement_real_texts.yaml` | 离线同义词替换与改写校验 |
| `workflows/text_question_augmentation.yaml` | `example_data/text/question_augmentation_real_questions.yaml` | 生成问题增强变体 |
| `workflows/text_multimodal_synthesis.yaml` | `example_data/multimodal/multimodal_real_samples.yaml` | 三阶段图文多模态合成 |

### 注意事项

- `README_zh.md` 为中文文档，`README.md` 为英文文档；两个文件应保持同等信息。
- 相对输入路径会按 workflow 配置文件所在目录的上一级项目根目录解析。
- `report_path` 目前保存在配置中，但实际报告由执行器写入输出目录下的 `report.md`。
- `text_llm_synthesis`、多模态和部分问题生成 workflow 依赖 OpenAI-compatible LLM 配置；未配置密钥时应先运行不依赖外部模型的 workflow 或仅执行 `validate`。
- `generated.jsonl` 只包含质量门控通过的 `accepted` 样本；过滤和失败样本在 `filtered.jsonl` 中用于审计。
- `runs/` 是运行产物目录，执行 `run` 会创建新目录；文档核查可优先使用 `validate` 和 `--help`，避免产生额外产物。

## 开发手册

### 项目结构

```text
DataStudio-HighQualityDataSynthesis/
├── configs/                  # 运行与模型注册配置
├── example_data/             # 公开最小样例与本地图片
├── docs/                     # 文档目录，当前包含 Workflow 配置说明
├── scripts/                  # 本地运行脚本
├── src/synthesis_engine/
│   ├── schemas/              # 输入、输出和 workflow JSON Schema
│   ├── cli/                  # Click 命令行入口
│   ├── accessors/            # LLM 与检索 QA 访问层
│   ├── llm/                  # OpenAI-compatible 客户端封装
│   ├── mappers/              # 文本合成 mapper 层
│   ├── operators/            # 文本、图像、结构化和质量算子
│   ├── prompts/              # Prompt 模板
│   └── runtime/              # 配置、输入适配、执行器、注册表、指标和报告
├── tests/                    # pytest 测试与真实 fixture
├── workflows/                # 可运行 workflow 示例
├── pyproject.toml            # 包元数据、依赖与命令行入口
└── uv.lock                   # uv 锁文件
```

### 开发自定义算子

自定义文本、图像、结构化或质量门控逻辑需要封装为 `BaseOperator` 子类，并通过 `custom_operators` 提供给 workflow 使用。建议把自定义插件统一放在 `workflows/plugins/`，例如 `workflows/plugins/my_synthesis_operator.py`；workflow 中统一使用 `./plugins/my_synthesis_operator.py`。

#### 1. 生成模板

```bash
mkdir -p workflows/plugins
uv run synthesis operator-template --type text --name my_synthesis_operator --output workflows/plugins/my_synthesis_operator.py
```

`--type` 支持 `text`、`image`、`structured`、`quality_gate`。`--name` 会写入类属性 `operator_name`，必须是 snake_case，并且需要和 workflow 的 `steps[].operator` 完全一致。

#### 2. 实现 BaseOperator

自定义算子继承 `synthesis_engine.operators.base.BaseOperator`，核心接口是：

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

执行器会把 step 的 `params` 传入 `self.config`，并依次调用 `setup()`、`process()`、`teardown()`。`process()` 读取 `item.prompt` 和 `item.payload`，把结果写入 `item.generated`，把质量、数量或调试信息写入 `item.metrics`，把问题写入 `item.issues`，必要时设置 `item.action` 为 `accepted`、`filtered`、`failed` 或 `needs_retry`。

#### 3. 按任务类型约定输出

| 算子类型 | 输入建议 | 输出建议 |
| --- | --- | --- |
| 文本算子 | 读取 `item.prompt`、`item.payload.topic`、`content`、`question`、`table` 等字段 | 写入 `item.generated["items"]` 或 `instruction/input/output/text`，并补充文本质量指标 |
| 图像算子 | 读取 `item.prompt`、`payload.image_path`、`payload.image_paths` 或图像生成参数 | 写入 `item.generated["image_path"]`、`image_prompt`、`negative_prompt` 等字段，并确认本地文件存在 |
| 结构化算子 | 读取 `payload.schema`、字段约束、分布参数或样例记录 | 写入 `item.generated["records"]` 或 `record`，并把字段覆盖率、分布信息写入 `metrics` |
| 质量门控算子 | 读取 `item.generated`、`item.metrics`、`item.issues` 和 `lineage.retry_attempt` | 设置 `item.action`；需要重试时用 `needs_retry`，最终不可发布时用 `filtered` |

不要删除 `id`、`task_type`、`prompt`、`payload`、`generated`、`metrics`、`issues`、`action`、`lineage` 等核心字段。需要并发不安全的资源时，在该 step 的 `params` 中设置 `concurrent: false`。

#### 4. 在 workflow 中接入

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

`validate` 会加载 `custom_operators` 并尝试创建每个 `steps[].operator`，因此它是发布前最小检查：

```bash
uv run synthesis validate -c workflows/custom_text_synthesis.yaml
uv run synthesis run -c workflows/custom_text_synthesis.yaml
uv run synthesis report -t runs/custom_text_synthesis
uv run synthesis trace -t runs/custom_text_synthesis --sample-id smoke_text_001
```

发布检查标准是：最小 seed 能跑通，`generated.jsonl` 中有可发布样本，`metrics.json` 中有自定义指标，`report.md` 可读，失败样本进入 `filtered.jsonl` 且带有可解释的 `issues`。

### 测试

```bash
uv run pytest
```

当前测试覆盖：

- workflow 配置加载和内置算子创建；
- Prompt 模板库默认加载、自定义目录覆盖与缺模板报错；
- 文本、图像、结构化和 mapper 层 workflow；
- raw text、JSON、CSV 等灵活输入适配；
- 自定义算子加载与 `operator-template`；
- 断点续跑、并发处理和重试逻辑。

也可以先运行轻量级文档核查命令：

```bash
uv run synthesis --help
uv run synthesis validate -c workflows/structured_synthesis.yaml
rg "synthesis (validate|run|report|trace|operator-template)" README_zh.md README.md
```

### 版权与许可证

- 本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。
