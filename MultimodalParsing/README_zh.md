<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">MultimodalParsing</h1>

<p align="center">
  <strong>DataReady · 多模态内容解析</strong><br>
  使用指南 · 将文档、图片与音频转为结构化内容。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-parse-0284c7.svg" alt="CLI: parse">
</p>

<p align="center">
  <a href="../README_zh.md">DataReady</a> &nbsp;·&nbsp;
  <a href="#dr-quick-start">快速开始</a> &nbsp;·&nbsp;
  <a href="#dr-cli">命令行</a> &nbsp;·&nbsp;
  <a href="README_dev_zh.md">开发指南</a> &nbsp;·&nbsp;
  <a href="README.md">English</a>
</p>

---

<details>
<summary><strong>本页目录</strong></summary>

- [模块简介](#dr-overview)
- [核心能力](#dr-features)
- [安装与环境](#dr-installation)
- [快速开始](#dr-quick-start)
- [命令行用法](#dr-cli)
- [输入与输出](#dr-输入与输出)
- [注意事项](#dr-注意事项)
- [版权与许可证](#dr-版权与许可证)
- [相关文档](#dr-documentation)

</details>

<a id="dr-overview"></a>

## 模块简介

MultimodalParsing 是一个轻量级多模态内容解析工作流引擎。它通过 YAML 工作流配置组织输入适配、端到端解析算子和运行报告；Markdown 重建、分块、质量评估等中间环节由端到端算子内部完成，适合将 PDF、Word、Excel、HTML、图片、音频以及结构化文本输入转换为统一的 JSONL 解析产物。

| 命令入口 | 示例工作流 | 数据类型 |
| --- | --- | --- |
| `parse` | [`pdf_parse.yaml`](workflows/pdf_parse.yaml) | PDF · Word · Excel · HTML · 图片 · 音频 |

<a id="dr-features"></a>

## 核心能力

- **配置驱动工作流**：通过 `workflows/*.yaml` 定义 `workflow`、`input`、`output`、`steps` 和可选 `custom_operators`。
- **多模态解析**：支持 PDF、Word、Excel、HTML、图片、音频文件输入，也支持 JSON、JSONL、CSV、stdin 和 raw_text 文本输入。
- **端到端解析算子**：`operators/` 只暴露 `pdf_parse`、`word_parse`、`excel_parse`、`html_parse`、`image_parse`、`audio_parse`；抽取、OCR、ASR、Markdown 重建、分块和质量评估均属于内部 workflow stage。
- **工具目录边界**：纯功能工具统一收敛到 `src/parse_engine/utilities/`；`operators/common/` 仅保留仍具有工作流公共能力的 operator 边界，Markdown 重建与分块的纯实现已下沉到 `utilities/markdown/`。
- **统一输出格式**：每个样本输出为 `DataItem`，包含 `id`、`modality`、`source`、`payload`、`metrics`、`issues`、`artifacts` 和 `action`。
- **运行可追踪**：每次运行写入 `artifacts.jsonl`、`failed.jsonl`、`metrics.json`、`report.md`、`workflow.yaml` 和 `checkpoint.json`。
- **断点续跑与并发**：`parse run` 支持 `--resume`，从 `output.path` 读取已有输出并跳过已完成样本；工作流可通过 `workflow.concurrency` 控制样本级并发。
- **自定义算子扩展**：`parse operator-template` 可生成自定义算子模板，工作流通过 `custom_operators` 加载。

<a id="dr-installation"></a>

## 安装与环境

### 依赖要求

- Python `>=3.10`；本地项目 `.python-version` 当前为 `3.13`。
- 推荐使用 `uv` 同步环境和运行命令。
- 运行依赖由 [`pyproject.toml`](pyproject.toml) 管理，包含 Click、Pydantic、PyYAML、python-docx、pandas、openpyxl、xlrd、Pillow、RapidOCR ONNX Runtime、soundfile、OpenAI SDK 等。
- 开发测试依赖：`pytest>=8.0`，通过 `dev` 可选依赖安装。

### 本地安装

```bash
cd MultimodalParsing
uv sync
```

安装后可使用 `parse` 脚本，也可以使用模块入口：

```bash
uv run parse --help
uv run python -m parse_engine --help
```

### 直接调用命令

如果 `parse` 已安装到系统 `PATH`，可直接调用：

```bash
parse --help
```

Windows PowerShell 中如未识别 `parse`，可先激活项目虚拟环境后再调用：

```powershell
.\.venv\Scripts\Activate.ps1
parse --help
```

<a id="dr-quick-start"></a>

## 快速开始

### 1. 校验工作流配置

```bash
uv run parse validate -c workflows/pdf_parse.yaml
```

成功时输出类似：

```text
OK: pdf_parse_v1 (1 steps)
```

### 2. 运行示例 PDF 解析

```bash
uv run parse run -c workflows/pdf_parse.yaml
```

公开示例 workflow 默认读取 `example_data/` 下的公开样例数据，不再依赖旧的内部 `data/` 目录。

命令会输出本次输出目录，例如：

```text
MultimodalParsing/runs/pdf_parse
```

### 3. 查看报告与追踪样本

```bash
uv run parse report -t runs/pdf_parse
uv run parse trace --sample-id html40 -t runs/pdf_parse
```

`report` 会打印输出目录下的 `report.md`；`trace` 会在 `artifacts.jsonl` 中按样本 id 或 artifact id 查找并输出 JSON。

<a id="dr-cli"></a>

## 命令行用法

### 命令总览

```bash
uv run parse --help
```

当前命令行包含以下子命令：

| 命令 | 用途 |
| --- | --- |
| `parse validate -c <workflow.yaml>` | 校验工作流配置、输入配置和算子引用是否可实例化。 |
| `parse run -c <workflow.yaml>` | 执行一次解析 workflow，并输出输出目录。 |
| `parse run -c <workflow.yaml> --resume` | 从 `output.path` 续跑，跳过已成功写入的样本。 |
| `parse operator-template --type <type> --name <name> --output <path>` | 生成自定义算子模板。 |
| `parse report -t <output_dir>` | 打印输出目录中的 `report.md`。 |
| `parse trace --sample-id <id> -t <output_dir>` | 查询样本或 artifact 的 JSON 结果。 |

### 自定义算子模板

```bash
uv run parse operator-template \
  # mkdir -p workflows/plugins
  --type text \
  --name my_parse_operator \
  --output workflows/plugins/my_parse_operator.py
```

`--type` 仅支持 `document`、`image`、`audio`、`text`、`quality_gate`。生成的 Python 文件需要在 workflow 中通过 `custom_operators` 引用，并在 `steps[].operator` 中使用对应的 snake_case 算子名。

<a id="dr-输入与输出"></a>

## 输入与输出

### 输入配置

工作流的 `input` 支持以下类型：

| `input.type` | 说明 |
| --- | --- |
| `auto` | 根据 `path` 或 `text` 自动推断输入类型。 |
| `file_dir` / `directory` | 递归读取目录中支持的非隐藏文件。 |
| `file` | 读取单个媒体、文本或结构化文件。 |
| `json` | 读取 JSON 对象或数组。 |
| `jsonl` | 按行读取 JSONL/NDJSON。 |
| `csv` | 按表头读取 CSV，每行生成一个样本。 |
| `stdin` | 从标准输入读取纯文本或 JSON。 |
| `raw_text` | 从 `input.text` 直接生成一个样本。 |

支持的媒体后缀包括 `.pdf`、`.docx`、`.xls`、`.xlsx`、`.html`、`.htm`、`.png`、`.jpg`、`.jpeg`、`.bmp`、`.webp`、`.wav`、`.mp3`、`.m4a`、`.flac`、`.aac`。

结构化输入可使用字段映射：

```yaml
input:
  type: csv
  path: data/input.csv
  id_field: sample_id
  modality_field: modality
  path_field: file_path
  text_field: content
```

### 示例工作流

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

项目已提供 `workflows/pdf_parse.yaml`、`workflows/word_parse.yaml`、`workflows/excel_parse.yaml`、`workflows/html_parse.yaml`、`workflows/image_parse.yaml`、`workflows/audio_parse.yaml` 作为公开示例工作流。

### 输出文件

每次 `parse run` 会直接在 `output.path` 下生成：

| 文件 | 说明 |
| --- | --- |
| `artifacts.jsonl` | 每行一个 `DataItem`，包含样本解析产物。 |
| `failed.jsonl` | 仅包含 `action == "failed"` 的样本。 |
| `metrics.json` | 总数、模态分布、artifact 类型、issue 类型、并发与续跑统计。 |
| `report.md` | Markdown 摘要报告，标题为 `Content Parsing Report`。 |
| `workflow.yaml` | 本次运行使用的工作流配置副本。 |
| `checkpoint.json` | 运行状态、已完成样本和续跑信息。 |

运行汇总遵循 `output.path/metrics.json` 输出，并在 `output.path/report.md` 中展示，核心字段包括：

- `input_total_count`：当前输入样本总数
- `total`：本次实际处理样本数
- `historical_completed_count`：当前输入中已由历史输出完成的样本数
- `newly_processed_count`：本次新增处理样本数
- `current_completed_count`：当前输入中已完成样本数
- `pending_count`：当前输入中仍未完成样本数

单条 `DataItem` 的核心结构与 `src/parse_engine/schemas/output_schema.json` 对齐：

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

<a id="dr-注意事项"></a>

## 注意事项

- `audio_parse` 内部 ASR 只读取当前 workflow `steps[].params.asr`。默认示例接入 DashScope `qwen3-asr-flash`，并通过 `DASHSCOPE_API_KEY` 读取密钥；若后端未配置或不可用，会记录 `asr_not_configured` issue，而不会生成占位转写文本。
- `pdf_parse` 和 `image_parse` 默认通过 workflow 中的 `params.document_parse` 调用 `openai_compatible` 多模态解析；如需工业文档解析服务，可切换 `provider: ocrflux`。OCRFlux 跨页合并响应使用安全字面量解析，并校验索引对类型与页面范围。
- `word_parse` 对 `.doc` / 伪 `docx` 需要通过 workflow 中的 `params.structure.soffice_command` 与 `params.media.soffice_command` 指定 LibreOffice 命令路径。
- 目录输入只读取支持后缀的非隐藏文件，并按路径排序以保持输出稳定。
- 相对 `input.path` 和 `output.path` 按 workflow 文件所在目录的上一级项目目录解析。
- `report_path` 当前作为配置字段保留；实际报告由执行器写入输出目录的 `report.md`。
- `trace` 的 `-t/--task` 可指向 `output.path`。
- 自定义算子的 `operator_name` 必须使用 snake_case，并与 workflow 的 `steps[].operator` 保持一致。

<a id="dr-版权与许可证"></a>

## 版权与许可证

- 本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。

<a id="dr-documentation"></a>

## 相关文档

- [使用指南](README_zh.md) · [开发指南](README_dev_zh.md)
- [Workflow 配置说明](docs/Workflow配置说明.md) · [示例工作流](workflows/)
- [示例数据来源](example_data/SOURCES.md) · [第三方依赖许可证清单](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">返回顶部</a> &nbsp;·&nbsp; <a href="../README_zh.md">DataReady 首页</a>
</p>
