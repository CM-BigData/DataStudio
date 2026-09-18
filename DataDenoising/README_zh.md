<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataDenoising</h1>

<p align="center">
  <strong>DataReady · 多模态数据去噪</strong><br>
  使用指南 · 清洗数据，并将样本分流至保留、剔除或人工复核。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-denoise-0284c7.svg" alt="CLI: denoise">
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
- [输入输出](#dr-输入输出)
- [Workflow 配置](#dr-workflow-配置)
- [注意事项](#dr-注意事项)
- [版权与许可证](#dr-版权与许可证)
- [相关文档](#dr-documentation)

</details>

<a id="dr-overview"></a>

## 模块简介

DataDenoising 是一个面向多模态数据清洗与质量路由的轻量工作流引擎。项目提供 `denoise` 命令行入口，可按配置读取文本、图片、图文对、视频等输入，执行内置或自定义去噪算子，并将样本分流到保留、剔除、人工复核三类输出。

项目包名为 `denoise-workflow-engine`，Python 包路径为 `denoise_workflow_engine`，默认正式 workflow 为 `workflows/denoise_auto.yaml`。

| 命令入口 | 示例工作流 | 数据类型 |
| --- | --- | --- |
| `denoise` | [`denoise_auto.yaml`](workflows/denoise_auto.yaml) | 文本 · 图片 · 图文对 · 视频 |

<a id="dr-features"></a>

## 核心能力

- **端到端能力边界**：内置 registry 只暴露 `text_denoise`、`image_denoise`、`image_text_pair_denoise`、`video_denoise`、`auto_denoise` 5 个端到端算子。
- **自动去噪编排**：`auto_denoise` 在内部完成防泄露检查、模态路由、质量评分和 action 决策，不把中间环节暴露为 workflow 算子。
- **工具目录边界**：解码、配置装配、内部 stage 执行辅助，以及各模态 `base.py` 这类纯工具底座统一放入 `src/denoise_workflow_engine/utilities/`；`operators/common/` 仅保留仍然是工作流公共算子的能力。
- **文本去噪**：支持编码检测、Unicode 修复、中文规范化、HTML/Markdown 清理、语言检测、长度/重复/低信息密度过滤、敏感信息识别与脱敏、语义质量评分和文本质量评分。
- **图片去噪**：支持图片解码、尺寸和比例检测、模糊/曝光/噪声检测、二维码、水印、Logo、安全风险、主体完整性、视觉质量评分和基础修复。
- **图文对去噪**：支持结构检查、OCR 接口、OCR 与文本一致性、关键字段一致性、关键词相似度、CLIP/VLM 一致性接口、安全融合和质量评分。
- **视频去噪**：支持视频探测、ffmpeg 解码、关键帧抽取、黑屏/模糊/冻结帧/二维码检测、音频抽取、音频质量、字幕 OCR、ASR 接口、关键帧 VLM、AIGC 检测、音画一致性、安全融合、修复和质量评分。
- **可扩展工作流**：支持 `pipeline` 和 `dag` 两种 workflow 模式，支持自定义算子文件、断点续跑、样本级并发和 Markdown 报告生成。

<a id="dr-installation"></a>

## 安装与环境

### 依赖要求

- Python >= 3.10
- 推荐使用 `uv` 管理环境和运行命令
- 视频相关算子依赖本机可用的 `ffmpeg` / `ffprobe`
- 主要 Python 依赖见 [`pyproject.toml`](pyproject.toml)：`numpy`、`opencv-python`、`Pillow`、`PyYAML`、`requests`、`id-validator`、`phonenumbers`、`email-validator`、`python-stdnum`、`validators`、`lingua-language-detector`、`scikit-image`、`ImageHash`、`rapidfuzz`、`regex`

### 本地安装

```bash
cd DataDenoising
uv sync
```

安装后可使用脚本入口：

```bash
uv run denoise --help
```

也可以直接使用模块入口：

```bash
uv run python -m denoise_workflow_engine.cli.main --help
```

### 直接调用命令

如果 `denoise` 已安装到系统 `PATH`，可直接调用：

```bash
denoise --help
```

Windows PowerShell 中如未识别 `denoise`，可先激活项目虚拟环境后再调用：

```powershell
.\.venv\Scripts\Activate.ps1
denoise --help
```

### 可选模型 API 配置

命令行运行时会加载本地 API 环境变量。示例文件位于：

```text
configs/api.env.example
```

可按需配置以下 OpenAI-compatible 接口变量：

- `LLM_API_*`：文本语义质量与文本修复
- `VLM_API_*`：图片安全、图片质量、图文一致性、视频关键帧描述
- `OCR_API_*`：图片 OCR 与视频字幕 OCR
- `CLIP_API_*`：图文相似度接口
- `ASR_API_*`：视频音频转写接口，需真实音频转写服务

所有 `*_API_BASE` 最终组成的远端接口地址必须使用 `http` 或 `https` 协议，并包含有效主机名。

未配置外部模型时，相关算子会使用项目内的本地兜底逻辑或证据不足的保守结果。

<a id="dr-quick-start"></a>

## 快速开始

### 1. 准备输入

正式 workflow 默认读取公开样例文件：

```text
example_data/input.jsonl
```

仓库已随默认 workflow 提供公开可分发的文本、图片、图文对和视频样例，可直接用于 `validate` 和公开 smoke run。替换为正式数据时保持 JSONL 每行一个样本即可。

每行是一个 JSON 对象，最小示例如下：

```jsonl
{"id":"text_001","payload":{"text":"待去噪文本内容，长度需要足够支撑质量判断。"}}
{"id":"image_001","payload":{"image_path":"example_data/assets/images/image_clean_dog.jpg"}}
{"id":"pair_001","payload":{"text":"图片描述文本","image_path":"example_data/assets/images/image_clean_dog.jpg"}}
{"id":"video_001","payload":{"video_path":"example_data/assets/videos/video_clean.mp4"}}
```

不要在正式输入中放入 `expected_action`、`expected_clean`、`ground_truth`、`manifest`、`reference_image_path`、`image_keywords`、`precomputed_ocr_text`、`precomputed_asr_text` 等答案或预计算提示字段。

### 2. 校验 workflow

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
```

成功时输出：

```text
workflow config is valid
```

### 3. 执行去噪

```bash
uv run denoise run -c workflows/denoise_auto.yaml
```

命令会打印 `workflow_id`、总量、保留/剔除/复核/失败数量，以及报告路径。

### 4. 查看报告

```bash
uv run denoise report -t outputs/latest
uv run denoise report -t outputs/latest --show
```

<a id="dr-cli"></a>

## 命令行用法

### `denoise validate`

校验 workflow 顶层结构、输入配置、步骤列表和算子名称。

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
```

参数：

- `-c, --config`：workflow 配置文件路径，必填。
- `--allow-root`：授权访问一个现有目录；可重复传入。默认授权当前工作目录。

### `denoise run`

执行 workflow。

```bash
uv run denoise run -c workflows/denoise_auto.yaml
uv run denoise run -c workflows/denoise_auto.yaml --resume
```

参数：

- `-c, --config`：workflow 配置文件路径，必填。
- `--resume`：启用断点续跑，跳过 `checkpoint.json` 中已完成的样本，并以追加模式写输出。
- `--allow-root`：授权 workflow 输入和输出访问一个现有目录；可重复传入。规范化路径必须位于授权根内。

### `denoise report`

读取运行目录中的 `metrics.json` 和 `report.md`，输出汇总信息。

```bash
uv run denoise report -t outputs/latest
uv run denoise report -t outputs/latest --show
```

参数：

- `-t, --run-dir`：包含 `metrics.json` 的运行目录，必填。
- `--show`：同时打印 `report.md` 全文。

### `denoise operator-template`

生成可加载的自定义算子模板。

```bash
mkdir -p workflows/plugins
uv run denoise operator-template --type text_denoise --name my_text_denoise --output workflows/plugins/my_text_denoise.py
```

参数：

- `--type`：端到端算子类型，必填；可选值为 `text_denoise`、`image_denoise`、`video_denoise`、`image_text_pair_denoise`、`auto_denoise`。
- `--name`：workflow 中使用的 snake_case 算子名，必填。
- `--output`：模板 Python 文件输出路径，必填。

生成后在 workflow 顶层加入：

```yaml
custom_operators:
  - ./plugins/my_text_denoise.py
steps:
  - id: my_text_filter
    operator: my_text_filter
    params: {}
```

### 路径边界

`denoise validate` 和 `denoise run` 默认只访问当前工作目录内的配置、输入和输出。命令行中的 workflow 配置和 `--allow-root` 在参数解析阶段转换为标准路径对象；workflow 相对路径仍按配置文件目录解析，随后执行真实路径规范化和授权根校验。解析结果越出当前工作目录时，使用 `--allow-root <directory>` 显式授权目标目录。JSON、JSONL、CSV 和 stdin 记录内的 `image_path`、`video_path`、`audio_path`、`reference_image_path` 与 `text_file` 也会规范化并校验授权根。修复产物和视频中间文件限制在本次 `output.run_dir` 或显式授权目录内，样本 ID 只能作为安全文件名组件使用。文件型 `custom_operators` 必须位于授权根内；模块型扩展应来自可信 Python 环境。`output.clean_path`、`output.dropped_path`、`output.review_path` 和 `output.report_path` 还必须位于规范化后的 `output.run_dir` 内。

<a id="dr-输入输出"></a>

## 输入输出

### 支持的输入类型

`src/denoise_workflow_engine/schemas/workflow_schema.json` 和 `InputAdapter` 支持以下 `input.type`：

- `auto`：按 `input.path` 类型和扩展名自动识别；当只有 `input.text` 时按 `raw_text` 处理。
- `jsonl`：逐行读取 JSON，对非法 JSON 行生成 `invalid_json` 复核样本。
- `json`：读取 JSON 对象或数组。
- `csv`：读取 CSV 行，可通过 `id_field`、`text_field`、`image_field`、`video_field`、`audio_field`、`modality_field` 映射字段。
- `directory`：递归读取目录下支持的文本、图片、视频、音频和结构化文件。
- `file`：读取单个文件，按扩展名识别文本、图片、视频、音频、JSON、JSONL 或 CSV。
- `stdin`：从标准输入读取。
- `raw_text`：直接读取 workflow 中的 `input.text`。

标准数据项至少包含：

```json
{
  "id": "sample_id",
  "payload": {
    "text": "文本内容",
    "image_path": "example_data/assets/images/image_clean_dog.jpg",
    "video_path": "example_data/assets/videos/video_clean.mp4"
  }
}
```

`payload.text` 与 `payload.image_path` 同时存在时会作为图文对处理。

### 输出目录

正式 workflow 的输出目录为：

```text
outputs/latest/
  clean.jsonl
  dropped.jsonl
  review.jsonl
  metrics.json
  operator_logs.jsonl
  checkpoint.json
  report.md
```

输出样本遵循 `src/denoise_workflow_engine/schemas/output_schema.json`，核心字段包括：

- `id`：样本 ID
- `modality`：识别后的模态
- `payload`：清洗后或保留的业务载荷
- `metrics`：算子写入的质量指标
- `issues`：问题标签列表
- `operator_trace`：算子级执行轨迹
- `action`：`keep`、`drop`、`review` 或 `pending`
- `quality_score`：质量评分

运行汇总遵循 `outputs/latest/metrics.json` 输出，并在 `outputs/latest/report.md` 中展示，核心字段包括：

- `input_total_count` / `total_count`：当前输入样本总数
- `current_run_count`：本次实际处理样本数
- `historical_completed_count`：当前输入中已由历史 checkpoint 完成的样本数
- `newly_processed_count`：本次新增处理样本数
- `current_completed_count`：当前输入中已完成样本数
- `pending_count`：当前输入中仍未完成样本数

<a id="dr-workflow-配置"></a>

## Workflow 配置

正式入口：

```text
workflows/denoise_auto.yaml
```

该文件使用 JSON 写法保存为 `.yaml`，包含：

- `workflow`：流程元信息，含 `id`、`name`、`mode`、`batch_size`、`concurrency`、`checkpoint`
- `input`：输入类型、路径和字段映射
- `output`：运行目录和输出文件名
- `custom_operators`：可选，自定义算子文件或模块路径
- `steps`：按顺序执行的算子列表；`mode: dag` 时可使用 `depends_on`

更多配置说明见 [`docs/Workflow配置说明.md`](docs/Workflow配置说明.md)。

<a id="dr-注意事项"></a>

## 注意事项

- 只能在正式输入中提供待处理数据，不要提供标准答案、预期动作、参考图或预计算 OCR/ASR/关键词字段。
- `workflows/denoise_auto.yaml` 的相对路径按 workflow 文件所在目录解析；当前公开主 workflow 已固定指向 `../example_data/input.jsonl` 和 `../outputs/latest/`。
- `--resume` 会依赖输出目录中的 `checkpoint.json` 跳过已完成样本，并追加写入已有输出文件。
- 外部模型 API key 不随项目提供；未配置 API 时，相关算子不会假定远端能力可用。
- 视频能力需要本机可执行 `ffmpeg`/`ffprobe`，否则相关视频样本可能进入复核或失败计数。
- `denoise validate` 只校验配置结构、输入路径和算子可创建性，不等价于完整运行。
- 输出到 `clean.jsonl` 不代表输入没有任何历史风险，只表示当前 workflow 的质量门决策为 `keep`。

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
