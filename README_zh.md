<a id="dr-top"></a>

<p align="center">
  <img src="asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="asset/divider-vertical.png" height="42" alt="">
  <img src="asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataReady</h1>

<p align="center">
  <strong>面向 AI 的多模态数据准备工具集</strong><br>
  解析 · 去重 · 去噪 · 评测 · 合成
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Toolkits-5-0284c7.svg" alt="5 toolkits">
</p>

<p align="center">
  <a href="#dr-features">核心能力</a> &nbsp;·&nbsp;
  <a href="#dr-quick-start">快速开始</a> &nbsp;·&nbsp;
  <a href="#dr-datasets">开放数据集</a> &nbsp;·&nbsp;
  <a href="#dr-documentation">文档</a> &nbsp;·&nbsp;
  <a href="README.md">English</a>
</p>

---

<a id="dr-overview"></a>

## 项目简介

**DataReady** 汇集五个独立的开源工作流引擎，帮助数据工程师和研究人员将文档、媒体与结构化记录转为可用于模型开发和下游应用的数据集。

每个模块均为独立 Python 项目，拥有各自的命令行入口。通过 **YAML 工作流**配置输入、输出、处理步骤和算子参数，通过 **自定义 Python 算子**扩展能力。运行结果包含结构化产物、指标与报告，并支持断点续跑。

你可以按需使用单个模块，也可以通过文件串联多个模块；串联时需将上一步的输出字段映射到下一步的输入配置。

<a id="dr-toolkits"></a>

## 工具目录

| 模块 | 数据类型 | 命令入口 |
| --- | --- | --- |
| **[多模态内容解析](MultimodalParsing/README_zh.md)**<br>`MultimodalParsing/` | PDF · Word · Excel · HTML · 图片 · 音频 | `parse` |
| **[智能数据去重](DataDeduplication/README_zh.md)**<br>`DataDeduplication/` | 文本 · 图片 · 音频 | `dedup` |
| **[多模态数据去噪](DataDenoising/README_zh.md)**<br>`DataDenoising/` | 文本 · 图片 · 图文对 · 视频 | `denoise` |
| **[数据质量评测](QualityEvaluation/README_zh.md)**<br>`QualityEvaluation/` | 文本 · 图像 · 音频 | `quality-eval` |
| **[高质量数据合成](DataSynthesis/README_zh.md)**<br>`DataSynthesis/` | 文本 · 图像 · 结构化 · 多模态 | `synthesis` |

<a id="dr-features"></a>

## 核心能力

### 多模态解析

[MultimodalParsing](MultimodalParsing/README_zh.md) 将 PDF、Word、Excel、HTML、图片和音频转换为结构化 JSONL 产物，涵盖内容抽取、OCR / ASR 集成、Markdown 重建、分块与质量评估。输出保留来源、内容、指标和问题，便于后续清洗与索引。

### 智能去重

[DataDeduplication](DataDeduplication/README_zh.md) 识别文本、图片和音频中的精确重复与近似重复。支持文本归一化、SimHash、MinHash LSH、图片感知哈希与结构相似度、音频指纹与声学相似度，并可接入向量、重排和 ASR 能力。输出重复簇、代表样本、保留与剔除记录及复核报告。

### 多模态去噪

[DataDenoising](DataDenoising/README_zh.md) 对文本、图片、图文对和视频执行清洗，并自动路由混合输入。支持文本规范化、标记清理、重复过滤与敏感信息脱敏，检查图片和视频的解码、分辨率、模糊、曝光、噪声等信号，以及图文一致性；按质量规则输出保留、剔除或待复核样本。

### 质量评测

[QualityEvaluation](QualityEvaluation/README_zh.md) 评估文本、图像和音频数据集，覆盖字段完整性、文本长度与标点、重复内容、图像完整性与标注，以及音频格式、采样率、削波、噪声和回声。输出质量评分、问题分布、国标质量维度映射、报告、算子追踪与错误队列。

### 数据合成

[DataSynthesis](DataSynthesis/README_zh.md) 基于种子数据、提示词和 Schema 生成样本，支持文本生成、文本与表格问答、同义替换、问题增强、结构化记录、图像和多模态合成。通过内部校验、多样性检查、质量门控与重试区分通过、过滤和失败结果，并记录指标、工作流副本与检查点。

> **外部模型配置**：OCR、ASR、Embedding、视觉或生成模型相关能力需要配置对应后端与凭据，具体依赖和输入输出要求见各模块文档。

<a id="dr-workflow"></a>

## 典型工作流程

```text
原始数据 → 内容解析 → 数据去重 → 数据去噪 → 质量评测 → 可用数据集
种子数据 → 数据合成 → 数据去重 / 去噪 / 评测 → 扩充数据集
```

按数据来源和使用目标选择步骤与顺序。模块通过文件衔接，输入输出格式以各自的工作流配置为准。

<a id="dr-installation"></a>

## 安装

**环境要求：** Python `>=3.10`，推荐使用 `uv`。视频去噪还需安装 `ffmpeg` / `ffprobe`。

在仓库根目录运行所需模块的安装命令；可按需选择，也可依次安装全部模块：

```bash
uv sync --project MultimodalParsing
uv sync --project DataDeduplication
uv sync --project DataDenoising
uv sync --project QualityEvaluation
uv sync --project DataSynthesis
```

每个模块使用独立环境。以上命令同样适用于 PowerShell；后续示例请先进入对应模块目录，再使用 `uv run`。

<a id="dr-quick-start"></a>

## 快速开始

下面使用**无需外部模型服务**的结构化数据合成示例。从仓库根目录执行：

```bash
cd DataSynthesis
uv sync
uv run synthesis validate -c workflows/structured_synthesis.yaml
uv run synthesis run -c workflows/structured_synthesis.yaml
uv run synthesis report -t runs/structured_synthesis
```

结果写入 `DataSynthesis/runs/structured_synthesis/`。完整输入、生成结果与报告说明见 [DataSynthesis 使用指南](DataSynthesis/README_zh.md)。

其他模块的命令入口（进入对应目录后执行）：

| 工作目录 | 查看帮助 |
| --- | --- |
| `MultimodalParsing/` | `uv run parse --help` |
| `DataDeduplication/` | `uv run dedup --help` |
| `DataDenoising/` | `uv run denoise --help` |
| `QualityEvaluation/` | `uv run quality-eval --help` |
| `DataSynthesis/` | `uv run synthesis --help` |

<a id="dr-datasets"></a>

## 开放数据集

我们在焕新社区(https://aihuanxin.cn/#/)同步开源了“梧桐·万象”系列五个数据集，覆盖跨文化语言、中华文化图像、模型安全、行业知识和科技行业语音。规模与说明沿用发布方介绍，完整内容及获取方式见各数据集页面。

| 数据集 | 规模 | 方向 |
| --- | --- | --- |
| [东南亚文化价值观平行语料](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-SoutheastAsia_CultureValue_Parallel_Corpus/type=org) | **180,000+** | 跨文化对齐 |
| [中国古诗词图文多模态数据集](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Poetry_Image_Multimodal_Dataset/type=org?tab=intro) | **9,900+** | 诗词与视觉表达 |
| [中文安全问答数据集](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Safety_QA_Dataset/type=org) | **200,000+** | 模型安全与对齐 |
| [能源专利数据集](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang_Energy_Patent_Dataset/type=org) | **90,000+** | 能源与低碳领域知识 |
| [科技行业合成语音多模态数据集](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Tech_Synthetic_Speech_Multimodal_Dataset/type=org) | **38,000+** | 科技行业语音合成与识别 |

展开查看数据内容与处理方式：

<details>
<summary><strong>东南亚文化价值观平行语料</strong></summary>

包含 **18 万余条文本记录**，聚焦东南亚跨文化对齐。同一社会文化话题呈现不同国家的视角，以中文和英文为语义锚点，加入相关国家的区域语言。JSON 记录包含多语言 `text` 对象及国家、话题、价值观类别等元数据。语料由语言模型生成与翻译，经过过滤和人工抽检，可用于区域语言模型、内容审核与跨文化对话。 [数据集详情](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-SoutheastAsia_CultureValue_Parallel_Corpus/type=org)。

</details>

<details>
<summary><strong>中国古诗词图文多模态数据集</strong></summary>

包含 **9,900 余组古诗词与插画配对**。每条记录将诗词、详细视觉描述与生成插画相连，并保留标题、朝代和作者信息。描述将诗词意象转化为具体场景、构图、艺术技法与氛围，支持文生图模型微调及古典文学与视觉表达研究。制作流程包含自动图文质量评估和人工抽检。 [数据集详情](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Poetry_Image_Multimodal_Dataset/type=org?tab=intro)。

</details>

<details>
<summary><strong>中文安全问答数据集</strong></summary>

包含 **20 万余条中文问答记录**，用于语言模型安全评估与对齐。每条 JSON 记录包含问题、回答、整体安全标签及八类风险标签，覆盖人身伤害、歧视偏见、违禁物品、欺诈盗窃、仇恨言论、虚假误导信息、不道德行为和隐私侵犯，同时包含安全与不安全样本。发布方将监督微调和基于人类反馈的强化学习列为适用场景，数据来源包括项目采集内容与部分 BeaverTails 数据。 [数据集详情](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Safety_QA_Dataset/type=org)。

</details>

<details>
<summary><strong>能源专利数据集</strong></summary>

包含能源与低碳领域 **9 万余项专利文本**。结构化记录涵盖标题、摘要、权利要求、说明书全文、公开与申请编号及日期、发明人、申请人和法律状态。`meta.field` 将记录归入 **14 类行业分类**，覆盖能源资源、环境保护、清洁能源、循环利用、绿色基础设施与碳管理。数据处理包含专利采集、行业标注、文本抽取和完整性检查，可为领域语言模型微调提供专业知识。 [数据集详情](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang_Energy_Patent_Dataset/type=org)。

</details>

<details>
<summary><strong>科技行业合成语音多模态数据集</strong></summary>

包含 **38,000+ 条文本与语音数据对**，覆盖信息技术、金融科技、智慧交通等科技行业领域，内容包含专业术语和公司机构名称。每条 JSON 记录通过 `audio_text` 与 `audio_path` 关联朗读文本和音频，并在 `meta` 中记录说话人性别、标识、采样率、位深、时长与领域标签。数据制作包括行业热词采集、专业语句自动生成和多说话人语音合成，音频采用统一的采样率与位深，可用于科技行业场景的语音合成与识别模型训练。 [数据集详情](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Tech_Synthetic_Speech_Multimodal_Dataset/type=org)。

</details>

> **数据与软件许可分开管理。** 数据集独立于本仓库分发，原发布页面标注为 **CC BY-NC 4.0**；软件采用 **MIT** 许可证。下载后，请按所选模块的输入配置映射文本、图片和元数据字段。

<a id="dr-documentation"></a>

## 文档导航

| 模块 | 使用指南 | 开发指南 | 配置参考 |
| --- | --- | --- | --- |
| **MultimodalParsing** | [使用指南](MultimodalParsing/README_zh.md) | [开发指南](MultimodalParsing/README_dev_zh.md) | [Workflow](MultimodalParsing/docs/Workflow配置说明.md) |
| **DataDeduplication** | [使用指南](DataDeduplication/README_zh.md) | [开发指南](DataDeduplication/README_dev_zh.md) | [Workflow](DataDeduplication/docs/Workflow配置说明.md) |
| **DataDenoising** | [使用指南](DataDenoising/README_zh.md) | [开发指南](DataDenoising/README_dev_zh.md) | [Workflow](DataDenoising/docs/Workflow配置说明.md) |
| **QualityEvaluation** | [使用指南](QualityEvaluation/README_zh.md) | [开发指南](QualityEvaluation/README_dev_zh.md) | [Workflow](QualityEvaluation/docs/Workflow配置说明.md) |
| **DataSynthesis** | [使用指南](DataSynthesis/README_zh.md) | [开发指南](DataSynthesis/README_dev_zh.md) | [Workflow](DataSynthesis/docs/Workflow配置说明.md) |

<a id="dr-license"></a>

## 许可证与版权

本项目采用 **MIT 许可证**，详见 [LICENSE](LICENSE)。

Copyright © 2026 中移动信息技术有限公司

---

<p align="center">
  <a href="#dr-top">返回顶部</a>
</p>
