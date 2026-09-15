# example_data 来源说明

本目录存放可公开随仓库发布的最小样例数据，用于运行 README workflow、单元测试和 smoke 验证。外部数据统一来自公开开放数据集；异常、重复、低清、模糊、空白、损坏和特殊字符样本均为这些开放数据集样本的本地加工变体。

## 开放数据集来源

| 数据类型 | 目录或文件 | 来源数据集 | 许可或来源说明 | 本地处理 |
| --- | --- | --- | --- | --- |
| 文本 | `text_dataset.jsonl`、`text_dataset.csv`、`text_consecutive_punctuation_sample/samples.jsonl`、`text_special_characters_sample/samples.jsonl`、`text_punctuation_pairing_sample/samples.jsonl` | Project Gutenberg / Alice's Adventures in Wonderland | Project Gutenberg 提供可免费访问和分发的电子文本；使用时遵循 Project Gutenberg License 和所在地版权规则。来源：https://www.gutenberg.org/ebooks/11；许可说明：https://www.gutenberg.org/policy/license.html | 截取开放文本短句，并加入空文本、重复、过长、缺字段、编码残留、特殊字符、连续标点和配对标点变体。 |
| 音频 | `audio_dataset/*.wav` | Mini LibriSpeech / LibriSpeech | Mini LibriSpeech 是 LibriSpeech 的回归测试子集，OpenSLR 标注许可为 CC BY 4.0。来源：https://www.openslr.org/31/ | 截取极小音频样本，用于音频格式、采样率、音量和噪声类 workflow 验证。 |
| 图像 | `image_dataset/*`、`image_aigc_eval_sample/*`、`image_blank_eval_sample/*` | Oxford-IIIT Pet Dataset | Oxford VGG 标注该数据集以 Creative Commons Attribution-ShareAlike 4.0 International License 发布，图片版权归原始所有者。来源：https://www.robots.ox.ac.uk/~vgg/data/pets/ | 复用猫照片，并派生缩放、重复、小尺寸、模糊、异常宽高比、BMP、PNG、裁剪、过曝空白、近纯色、边缘图、posterize 风格图和损坏图片样本。 |

## 本地加工变体

| 目录或文件 | 基础来源 | 加工方式 | 用途 |
| --- | --- | --- | --- |
| `text_dataset.jsonl`、`text_dataset.csv` 中的异常记录 | Project Gutenberg 开放文本短句 | 添加空文本、缺字段、重复片段、长文本、编码残留和缺失 ID | 触发文本完整性、长度、重复、字符异常和标签检查。 |
| `text_consecutive_punctuation_sample/samples.jsonl` | Project Gutenberg 开放文本短句 | 插入允许或异常的连续标点 | 验证连续标点检查。 |
| `text_special_characters_sample/samples.jsonl` | Project Gutenberg 开放文本短句 | 插入 BOM、零宽字符、软连字符、控制字符、word joiner 和编码残留 | 验证特殊字符检查。 |
| `text_punctuation_pairing_sample/samples.jsonl` | Project Gutenberg 开放文本短句 | 插入成对或未闭合的引号、括号和方括号 | 验证标点配对检查。 |
| `image_dataset/img_good_dup.jpg` | Oxford-IIIT Pet 图像 | 复制同图像内容 | 触发 `duplicate_image`。 |
| `image_dataset/img_small.png` | Oxford-IIIT Pet 图像 | 缩放到低分辨率 | 触发宽高过小。 |
| `image_dataset/img_blur.jpg` | Oxford-IIIT Pet 图像 | 模糊处理 | 触发清晰度检查。 |
| `image_dataset/img_wide.jpg` | Oxford-IIIT Pet 图像 | 裁剪或缩放成异常宽高比 | 触发宽高比检查。 |
| `image_dataset/img_blank.jpg`、`image_blank_eval_sample/scan_blank_page.jpg`、`image_blank_eval_sample/scan_blank_page_crop.jpg`、`image_blank_eval_sample/white_wall_background_crop.png` | Oxford-IIIT Pet 图像 | 过曝、低对比度或近纯色加工 | 触发空白图、近纯色图检查。 |
| `image_dataset/corrupted.jpg` | Oxford-IIIT Pet 图像 | 写入损坏图片内容 | 触发图片解码和完整性检查。 |
| `image_aigc_eval_sample/illustration_logo.jpg`、`image_aigc_eval_sample/scanned_page.jpg`、`image_aigc_eval_sample/suspected_aigc_weak.jpg` | Oxford-IIIT Pet 图像 | posterize、边缘提取、裁剪、平滑和色彩增强 | 验证 AIGC 指标链路。 |
| `image_dataset/annotations.json` 中的 `missing_file.jpg` 记录 | Oxford-IIIT Pet 图像目录样例 | 仅声明不存在的文件名 | 触发 `image_not_found`。 |
| `image_text_consistency.jsonl` | Oxford-IIIT Pet 图像和 Project Gutenberg 派生文本 | 组合开放数据集图像路径和说明文本 | 验证图文一致性 workflow 的输入读取。 |

## 使用约束

- 样例数据只用于本仓库 workflow 示例、测试和 smoke 验证。
- 开放数据集样本保留来源和许可说明；使用完整外部数据集时应以对应官方网站或源仓库的许可条款为准。
- 本地加工变体不改变原始开放数据集样本的来源归属。
