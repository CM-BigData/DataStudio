<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">MultimodalParsing</h1>

<p align="center">
  <strong>DataReady · 多模态内容解析</strong><br>
  开发指南 · 将文档、图片与音频转为结构化内容。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-parse-0284c7.svg" alt="CLI: parse">
</p>

<p align="center">
  <a href="../README_zh.md">DataReady</a> &nbsp;·&nbsp;
  <a href="#dr-project-structure">项目结构</a> &nbsp;·&nbsp;
  <a href="#dr-custom-operators">自定义算子</a> &nbsp;·&nbsp;
  <a href="README_zh.md">使用指南</a> &nbsp;·&nbsp;
  <a href="README_dev.md">English</a>
</p>

---

<details>
<summary><strong>本页目录</strong></summary>

- [模块简介](#dr-overview)
- [项目结构](#dr-project-structure)
- [开发自定义算子](#dr-custom-operators)
- [OCRFlux 响应校验](#dr-ocrflux-响应校验)
- [验证与测试](#dr-testing)
- [相关文档](#dr-documentation)

</details>

<a id="dr-overview"></a>

## 模块简介

MultimodalParsing 是一个轻量级多模态内容解析工作流引擎。它通过 YAML 工作流配置组织输入适配、端到端解析算子和运行报告；Markdown 重建、分块、质量评估等中间环节由端到端算子内部完成，适合将 PDF、Word、Excel、HTML、图片、音频以及结构化文本输入转换为统一的 JSONL 解析产物。

| 命令入口 | 示例工作流 | 数据类型 |
| --- | --- | --- |
| `parse` | [`pdf_parse.yaml`](workflows/pdf_parse.yaml) | PDF · Word · Excel · HTML · 图片 · 音频 |

<a id="dr-project-structure"></a>

## 项目结构

```text
MultimodalParsing/
├── pyproject.toml                 # 包元数据、依赖和 parse命令行入口
├── example_data/                  # 面向大众的公开样例数据
├── docs/                          # 文档目录：验收标准、Workflow 配置说明、算子清单等
├── src/parse_engine/
│   ├── cli/main.py                # Click command-line：validate/run/operator-template/report/trace
│   ├── models.py                  # DataItem、Artifact、SourceTrace
│   ├── schemas/                   # 输入、输出、workflow JSON Schema
│   ├── runtime/                   # 配置、输入适配、执行器、注册表、报告和 checkpoint
│   ├── utilities/                 # 纯工具与编排辅助实现
│   │   ├── document/              # 文档解析服务客户端
│   │   ├── markdown/              # Markdown chunker、重建器与分块 artifact 构造工具
│   │   └── pipeline.py            # 通用 pipeline 编排辅助
│   └── operators/                 # 端到端解析算子
│       ├── common/                # 跨格式共用内部能力
│       │   ├── markdown/          # Markdown workflow stage 边界（薄 operator 壳）
│       │   └── parse_quality.py   # 解析质量评估
│       ├── pdf_parse/             # PDF operator、pipeline 和文档抽取逻辑
│       ├── word_parse/            # Word operator、pipeline 和文档结构抽取逻辑
│       ├── excel_parse/           # Excel operator、pipeline 和表格结构抽取逻辑
│       ├── html_parse/            # HTML operator、pipeline 和正文抽取逻辑
│       ├── image_parse/           # 图片 operator、pipeline、metadata 和 OCR 逻辑
│       └── audio_parse/           # 音频 operator、pipeline、metadata 和 ASR
│           └── asr/               # ASR backend/factory/result 适配
├── tests/                         # pytest 单元测试和工作流回归测试
└── workflows/                     # 示例与验证工作流 YAML
```

<a id="dr-custom-operators"></a>

## 开发自定义算子

### 运行 workflow

只需要准备输入数据和 workflow YAML，然后按固定入口校验、运行、查看结果：

```bash
uv run parse validate -c workflows/pdf_parse.yaml
uv run parse run -c workflows/pdf_parse.yaml
uv run parse report -t runs/pdf_parse
uv run parse trace --sample-id html40 -t runs/pdf_parse
```

workflow 的 `steps[].operator` 引用已经注册的端到端算子名。内置端到端算子在命令行启动时自动注册；外部算子必须先在同一个 workflow 的 `custom_operators` 中声明。

### 开发流程

自定义扩展需要提供一个可加载的端到端 Python 算子文件和一个最小 workflow 样本。推荐把自定义插件统一放在 `workflows/plugins/`，这样 `custom_operators` 可以稳定使用相对路径。

1. 生成模板：

```bash
mkdir -p workflows/plugins
uv run parse operator-template \
  --type text \
  --name my_parse_operator \
  --output workflows/plugins/my_parse_operator.py
```

2. 在模板中继承 `BaseOperator`，保持 `operator_name` 为 snake_case，并实现 `process(self, item)`：

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

`BaseOperator` 会接收 workflow step 的 `params` 并保存到 `self.config`。需要加载模型、连接资源或释放资源时，可覆盖 `setup()` 和 `teardown()`；批处理默认由 `process_batch()` 逐条调用 `process()`。

3. 在 workflow 中接入：

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

`custom_operators` 支持 Python 文件路径或可 import 的模块名。相对路径按 workflow YAML 所在目录解析；`input.path` 和 `output.path` 的相对路径按 workflow 文件所在目录的上一级项目目录解析。`steps[].operator` 必须等于类上的 `operator_name`，否则 `parse validate` 会报 unknown operator。

### 输出与验收约定

自定义算子应把结构化解析结果写入 `item.artifacts`，把计数、分数、耗时等统计写入 `item.metrics`，把诊断问题写入 `item.issues`，并把最终状态写到 `item.action`。执行完成后会统一生成：

| 输出 | 来源 |
| --- | --- |
| `artifacts.jsonl` | 每个 `DataItem` 的 `artifacts`、`metrics`、`issues` 和 `action`。 |
| `failed.jsonl` | `action == "failed"` 的样本。 |
| `metrics.json` | 本次运行汇总的数量、模态、artifact 类型、issue 类型、并发和续跑指标。 |
| `report.md` | 基于本次运行结果生成的 Markdown 报告。 |

发布前至少运行一个最小样本验证：

```bash
uv run parse validate -c workflows/custom_parse.yaml
output_dir=$(uv run parse run -c workflows/custom_parse.yaml)
uv run parse report -t "$output_dir"
sample_id=$(python -c 'import json,sys; print(json.loads(open(sys.argv[1], encoding="utf-8").readline())["id"])' "$output_dir/artifacts.jsonl")
uv run parse trace --sample-id "$sample_id" -t "$output_dir"
```

`raw_text` 输入的样本 id 由输入适配器生成；文件、JSONL、CSV 等输入也可能来自文件名或映射字段。发布验证时应使用实际生成的 `DataItem.id`，也可以使用 artifact id 追踪单条产物。

<a id="dr-ocrflux-响应校验"></a>

## OCRFlux 响应校验

OCRFlux 跨页元素合并只接受由整数索引对组成的列表。响应通过 Python 标准库 `ast.literal_eval` 解析，并在进入页面合并流程前校验数据形状和索引范围；响应内容不会作为 Python 表达式执行。

<a id="dr-testing"></a>

## 验证与测试

运行完整测试：

```bash
uv run pytest
```

运行重点回归测试：

```bash
uv run pytest tests/test_config.py tests/test_flexible_input_custom_operator.py
uv run pytest tests/test_pdf_operator.py tests/test_word_workflow.py tests/test_excel_workflow.py
uv run pytest tests/test_html_operator.py
uv run pytest -q
```

测试覆盖工作流配置加载、端到端算子注册、PDF/Word/Excel/HTML 解析、内部 Markdown 分块、内部音频 ASR stage、灵活输入适配、自定义端到端算子加载、command-line `operator-template` 和 `validate` 行为。

<a id="dr-documentation"></a>

## 相关文档

- [使用指南](README_zh.md) · [开发指南](README_dev_zh.md)
- [Workflow 配置说明](docs/Workflow配置说明.md) · [示例工作流](workflows/)
- [示例数据来源](example_data/SOURCES.md) · [第三方依赖许可证清单](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">返回顶部</a> &nbsp;·&nbsp; <a href="../README_zh.md">DataReady 首页</a>
</p>
