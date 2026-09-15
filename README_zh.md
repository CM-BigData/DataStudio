# DataStudio

> English version: [README.md](README.md)

DataStudio 汇总 5 个独立的开源数据工具集，可在同一台机器上分别安装，并按各自的命令入口运行 workflow。

## 工具目录

根目录下包含以下工具目录：

| 目录 | 命令入口 | 用途 |
| --- | --- | --- |
| `DataStudio-MultimodalContentParsing/` | `parse` | 解析 PDF、Word、Excel、HTML、图片、音频等内容 |
| `DataStudio-IntelligentDataDeduplication/` | `dedup` | 对文本、图片、音频样本执行去重 |
| `DataStudio-AllModalIntelligentDataDenoising/` | `denoise` | 对文本、图片、图文对、视频等数据执行清洗与分流 |
| `DataStudio-NationalStandardDataQualityEvaluation/` | `quality-eval` | 对文本、图像和音频数据集执行质量检查 |
| `DataStudio-HighQualityDataSynthesis/` | `synthesis` | 执行文本、图像、结构化和多模态数据合成 workflow |

## 环境要求

- Python `>=3.10`
- 推荐使用 `uv`

## 安装

在根目录依次执行：

```bash
cd DataStudio-MultimodalContentParsing && uv sync && cd ..
cd DataStudio-IntelligentDataDeduplication && uv sync && cd ..
cd DataStudio-AllModalIntelligentDataDenoising && uv sync && cd ..
cd DataStudio-NationalStandardDataQualityEvaluation && uv sync && cd ..
cd DataStudio-HighQualityDataSynthesis && uv sync && cd ..
```

Windows PowerShell 也推荐直接使用 `uv` 命令；如需使用命令入口，先进入对应目录并激活 `.venv`。

## 快速开始

先确认 5 个命令入口可用：

```bash
cd DataStudio-MultimodalContentParsing && uv run parse --help && cd ..
cd DataStudio-IntelligentDataDeduplication && uv run dedup --help && cd ..
cd DataStudio-AllModalIntelligentDataDenoising && uv run denoise --help && cd ..
cd DataStudio-NationalStandardDataQualityEvaluation && uv run quality-eval --help && cd ..
cd DataStudio-HighQualityDataSynthesis && uv run synthesis --help && cd ..
```

然后按需要进入单个子项目，运行对应 workflow。完整的 workflow 示例、输入输出说明和环境变量配置见各子项目的 `README_zh.md`。

## 子项目文档

- [DataStudio-MultimodalContentParsing](DataStudio-MultimodalContentParsing/README_zh.md)
- [DataStudio-IntelligentDataDeduplication](DataStudio-IntelligentDataDeduplication/README_zh.md)
- [DataStudio-AllModalIntelligentDataDenoising](DataStudio-AllModalIntelligentDataDenoising/README_zh.md)
- [DataStudio-NationalStandardDataQualityEvaluation](DataStudio-NationalStandardDataQualityEvaluation/README_zh.md)
- [DataStudio-HighQualityDataSynthesis](DataStudio-HighQualityDataSynthesis/README_zh.md)

## 许可证与版权

License: MIT

Copyright © 2026 中移动信息技术有限公司
