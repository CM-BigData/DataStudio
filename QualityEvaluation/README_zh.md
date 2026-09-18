<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">QualityEvaluation</h1>

<p align="center">
  <strong>DataReady · 数据质量评测</strong><br>
  使用指南 · 通过可追踪的评分与报告评估数据集质量。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-quality--eval-0284c7.svg" alt="CLI: quality-eval">
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
- [输入与 workflow 配置](#dr-输入与-workflow-配置)
- [输出结果](#dr-输出结果)
- [公开端到端算子](#dr-公开端到端算子)
- [运行质量评测 workflow](#dr-运行质量评测-workflow)
- [版权与许可证](#dr-版权与许可证)
- [相关文档](#dr-documentation)

</details>

<a id="dr-overview"></a>

## 模块简介

QualityEvaluation 是一个基于 workflow 的轻量级数据质量评测工具，包名为 `quality-eval-workflow-engine`，命令入口为 `quality-eval`。当前实现面向文本、图像和音频数据集，支持通过 YAML/JSON workflow 调用端到端算子，对样本进行结构、完整性、长度、异常字符、重复、图片格式、分辨率、清晰度、空白图、疑似 AI 生成图、标注 bbox、音频格式、采样率、位深、音量、噪声、回声等质量检查，并输出样本级结果、汇总 JSON、Markdown 报告、算子追踪日志、checkpoint 和错误队列。

| 命令入口 | 示例工作流 | 数据类型 |
| --- | --- | --- |
| `quality-eval` | [`text_dataset_eval.yaml`](workflows/text_dataset_eval.yaml) | 文本 · 图像 · 音频 |

<a id="dr-features"></a>

## 核心能力

- **文本质量评测**：支持 JSONL、CSV 和可映射字段输入，覆盖字段完整性、文本长度、异常 Unicode、低质量重复片段、连续标点、特殊字符、标点配对、文本重复、标签完整性和文本评分。
- **图像质量评测**：支持图片目录加 `annotations.json`，覆盖解码、无损完整性、格式白名单、分辨率、长宽比、清晰度、空白图、疑似 AI 生成图、图文关联性、重复图片、标签完整性和 bbox 越界检查。
- **音频质量评测**：支持音频目录或表格输入，覆盖解码、格式白名单、采样率、位深、音量动态范围、削波、噪声、回声、重复音频和音频评分。
- **Workflow 执行**：按公开端到端算子注册名组织步骤，内部检查步骤由端到端算子编排。
- **工具目录边界**：`src/quality_eval/utilities/` 仅放纯工具/helper，例如评分规则、评测编排通用助手和图像/文本共享函数；图像/文本数据集端到端业务编排分别保留在 `src/quality_eval/operators/image_dataset_eval/pipeline.py` 与 `src/quality_eval/operators/text_dataset_eval/pipeline.py`；`operators/common/` 仅保留 `BaseOperator` 这类仍具工作流公共语义的基类。
- **可追踪输出**：每条样本结果包含 `trace_id`、`trace_summary` 和算子级 `trace`，同时写入独立算子日志。
- **断点续跑**：`run --resume` 会复用已有结果并跳过已完成样本，统计区分输入总数、本次运行样本数、历史已完成数、本次处理数、当前已完成数和待处理数。
- **自定义算子**：`operator-template` 可生成文本、图像、评分或治理类算子模板，workflow 可通过 `custom_operators` 加载。

<a id="dr-installation"></a>

## 安装与环境

### 依赖要求

- Python >= 3.10
- 运行依赖：`PyYAML>=6.0`、`Pillow>=12.3.0`、`regex>=2026.5.9`
- 测试依赖：`pytest>=8.0.0`，通过 `test` 可选依赖安装。

### 本地安装

```bash
cd QualityEvaluation
uv sync
uv run quality-eval --help
```

如果不使用已安装的脚本入口，也可以通过模块方式执行：

```bash
uv run python -m quality_eval --help
```

### 直接调用命令

如果 `quality-eval` 已安装到系统 `PATH`，可直接调用：

```bash
quality-eval --help
```

Windows PowerShell 中如未识别 `quality-eval`，可先激活项目虚拟环境后再调用：

```powershell
.\.venv\Scripts\Activate.ps1
quality-eval --help
```

<a id="dr-quick-start"></a>

## 快速开始

### 1. 校验示例 workflow

```bash
uv run quality-eval validate-config -c workflows/text_dataset_eval.yaml
uv run quality-eval validate-config -c workflows/image_dataset_eval.yaml
```

成功时会输出：

```text
valid_config=workflows/text_dataset_eval.yaml
```

### 2. 执行文本数据集评测

```bash
uv run quality-eval run -c workflows/text_dataset_eval.yaml --task-id local_text --output-dir outputs/local_text
```

命令会打印本次任务的核心产物路径：

```text
task_id=local_text
result_path=outputs/local_text/text_eval_result.jsonl
summary_path=outputs/local_text/text_eval_summary.json
report_path=outputs/local_text/text_eval_report.md
```

### 3. 执行图像数据集评测

```bash
uv run quality-eval run -c workflows/image_dataset_eval.yaml --task-id local_image --output-dir outputs/local_image
```

<a id="dr-cli"></a>

## 命令行用法

```bash
quality-eval run -c <workflow.yaml> [--task-id <id>] [--output-dir <dir>] [--resume] [--workers <n>] [--allow-root <dir>]
quality-eval validate-config -c <workflow.yaml> [--allow-root <dir>]
quality-eval list-operators
quality-eval export-report -t <run-dir-or-summary-json> [-o <report.md>] [--allow-root <dir>]
quality-eval operator-template --type text|image|score|governor --name <snake_case_name> --output <file.py> [--allow-root <dir>]
```

### 子命令说明

| 命令 | 作用 |
|---|---|
| `run` | 加载 workflow，执行完整质量评测，并写出结果、汇总、报告、日志、checkpoint 和错误队列。 |
| `validate-config` | 校验 workflow 结构、算子注册名和输入路径。 |
| `list-operators` | 打印当前已注册算子名。 |
| `export-report` | 从汇总 JSON 或运行目录重新生成 Markdown 报告。 |
| `operator-template` | 生成自定义算子模板文件。 |

### 路径授权

涉及文件系统路径的子命令默认只访问当前工作目录。使用可重复的 `--allow-root <directory>` 可授权其他现有目录。命令行路径参数在参数解析阶段转换为标准路径对象，配置内路径随后执行真实路径规范化和授权根边界检查。配置、输入、输出、报告、记录内 `image_path`/`audio_path`、图片 annotation 路径和文件型 `custom_operators` 规范化后必须位于当前工作目录或授权目录内。模块型扩展应来自可信 Python 环境。`--task-id` 只接受字母、数字、点、下划线和连字符，同时拒绝 Windows 保留设备名；派生的 checkpoint、日志和错误队列文件会再次限制在各自输出目录内。图文一致性使用远端模型时，`rules.image_text_consistency_model_revision` 必须填写经过审核的不可变提交哈希，模型加载不会执行远端自定义代码。

<a id="dr-输入与-workflow-配置"></a>

## 输入与 workflow 配置

Workflow 支持 YAML/JSON，示例位于 `workflows/`。

| 配置段 | 说明 |
|---|---|
| `workflow` | workflow id、名称、执行模式、任务类型、batch、并发和 checkpoint 开关。 |
| `runtime` | 执行器类型、worker 数、batch size 和失败重试次数。 |
| `input` | 输入类型和路径；文本示例支持 `jsonl`、`csv`，图像示例使用 `image_folder`。 |
| `output` | 样本结果 JSONL、汇总 JSON 和 Markdown 报告路径。 |
| `rules` | 质量阈值和算子参数。 |
| `score_weights` | 综合评分权重。 |
| `steps` | workflow 步骤，`operator` 必须匹配注册算子名。 |

文本样例：

```yaml
input:
  type: jsonl
  path: ./example_data/text_dataset.jsonl
```

CSV 样例：

```yaml
input:
  type: csv
  path: ./example_data/text_dataset.csv
```

图像样例：

```yaml
input:
  type: image_folder
  path: ./example_data/image_dataset
  annotation_path: ./example_data/image_dataset/annotations.json
```

统一输入样本至少包含 `id`、`modality`、`source`、`payload`、`meta`、`metrics`、`issues`、`action`。相对路径会优先按 workflow 文件所在目录解析；如果不存在，再按项目根目录解析。

<a id="dr-输出结果"></a>

## 输出结果

`run` 会根据 workflow 的 `output` 段写出以下文件；使用 `--output-dir` 时会保留配置中的文件名并替换目录。

| 产物 | 说明 |
|---|---|
| `*_result.jsonl` | 样本级结果，每行一个 JSON 对象。 |
| `*_summary.json` | 数据集级汇总，包括计数、分数、问题分布、样本列表、国标维度映射和追踪信息。 |
| `*_report.md` | 根据汇总 JSON 生成的 Markdown 报告。 |
| `checkpoints/<task_id>.json` | 断点续跑状态。 |
| `logs/<task_id>_operators.jsonl` | 算子级执行追踪日志。 |
| `errors/<task_id>_errors.jsonl` | 算子异常样本错误队列。 |

样本级输出字段与 `src/quality_eval/schemas/output_schema.json` 对齐，核心字段包括 `task_id`、`sample_id`、`modality`、`status`、`score`、`level`、`metrics`、`issues`、`action`、`suggestions`，并额外包含 `trace_id`、`trace_summary` 和 `trace`。

<a id="dr-公开端到端算子"></a>

## 公开端到端算子

`src/quality_eval/operators/` 只保留可在 workflow 中直接使用的端到端算子：

- `text_dataset_eval`：文本数据集端到端质量评测，内部包含 schema、完整性、长度、字符、重复、标点、标签和评分等检查。
- `image_dataset_eval`：图像数据集端到端质量评测，内部包含解码、无损完整性、格式、分辨率、长宽比、清晰度、重复、标注、空白图、AIGC、图文关联性和评分等检查。
- `audio_dataset_eval`：音频数据集端到端质量评测，内部包含解码、格式、采样率、位深、音量动态范围、削波、噪声、回声、重复和评分等检查。

单项检查属于内部 workflow step，不在 `list-operators` 中公开。需要只运行部分检查时，在端到端算子的 `params.enabled_checks` 中声明，例如 `blank`、`aigc`、`special_characters` 或 `punctuation_pairing`。

可用算子以实际命令输出为准：

```bash
uv run quality-eval list-operators
```

<a id="dr-运行质量评测-workflow"></a>

## 运行质量评测 workflow

不需要改代码，只需要准备输入数据、workflow 配置和输出目录。

1. 选择或复制一个 workflow，例如 `workflows/text_dataset_eval.yaml` 或 `workflows/image_dataset_eval.yaml`。
2. 在 `input` 中声明数据来源；文本常用 `jsonl`、`csv`、`raw_text`，图像常用 `image_folder` 加 `annotation_path`。
3. 在 `steps` 中声明一个端到端评测步骤，`steps[].operator` 必须是 `uv run quality-eval list-operators` 能看到的注册名。
4. 运行前先校验配置：

```bash
uv run quality-eval validate-config -c workflows/text_dataset_eval.yaml
```

5. 运行 workflow，并传入稳定的任务号和输出目录：

```bash
uv run quality-eval run -c workflows/text_dataset_eval.yaml --task-id <workflow-task-id> --output-dir <workflow-output-dir>
```

建议把 `--task-id` 对齐任务 ID，把 `--output-dir` 对齐该任务的结果目录。`--output-dir` 会保留 workflow 中 `output.result_path`、`output.summary_path`、`output.report_path` 的文件名，并把目录替换为指定目录。一次运行会写出 `*_result.jsonl`、`*_summary.json`、`*_report.md`，并在 summary 同级目录下派生 `logs/<task_id>_operators.jsonl`、`errors/<task_id>_errors.jsonl` 和 `checkpoints/<task_id>.json`。

已有 summary 后，可以重新导出报告：

```bash
uv run quality-eval export-report -t outputs/local_text/text_eval_summary.json -o outputs/local_text/text_eval_report.md
uv run quality-eval export-report -t outputs/local_text
```

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
