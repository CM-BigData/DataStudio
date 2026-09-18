<a id="dr-top"></a>

# 示例资源目录

[DataReady](../../../README_zh.md) / [DataDenoising](../../README_zh.md) / 示例资源

本目录存放公开示例输入引用的图片与视频素材，用于运行多模态去噪工作流。

## 资源导航

| 资源 | 用途 |
| --- | --- |
| [images/](images/) | 图片与图文对示例素材 |
| [videos/](videos/) | 视频示例素材 |
| [input.jsonl](../input.jsonl) | 公开主工作流默认读取的样本清单 |
| [SOURCES.md](../SOURCES.md) | 公开素材的来源与使用说明 |

## 使用说明

- 默认工作流为 [`denoise_auto.yaml`](../../workflows/denoise_auto.yaml)，读取 [`example_data/input.jsonl`](../input.jsonl)。
- 本目录仅存放上述 JSONL 引用的公开素材加工资源，不包含答案字段或预计算提示字段。
- 运行步骤、输入格式与环境要求见 [DataDenoising 使用指南](../../README_zh.md)。
