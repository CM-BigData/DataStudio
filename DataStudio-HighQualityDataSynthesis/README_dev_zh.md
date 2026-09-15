# DataStudio-HighQualityDataSynthesis

> English version: [README_dev.md](README_dev.md)

DataStudio-HighQualityDataSynthesis 是一个面向高质量数据合成任务的轻量级工作流引擎。项目通过 YAML workflow 编排输入适配、文本/图像/结构化数据合成、端到端合成算子、内部质量闭环、重试、断点续跑和报告输出，安装后提供 `synthesis` 命令行入口。


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

### 模型端点安全

OpenAI-compatible 客户端在配置解析和 SDK 客户端创建阶段校验端点。携带 API 密钥的远程端点必须使用 HTTPS；HTTP 仅允许连接 `localhost`、`127.0.0.1` 或 `::1`。公开 workflow 通过 `api_base_env` 与 `api_key_env` 引用环境变量，不固化远程服务地址或密钥。

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
