<a id="dr-top"></a>

<p align="center">
  <img src="asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="asset/divider-vertical.png" height="42" alt="">
  <img src="asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataReady</h1>

<p align="center">
  <strong>Multimodal Data Preparation for AI</strong><br>
  Parse · Deduplicate · Denoise · Evaluate · Synthesize
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/Toolkits-5-0284c7.svg" alt="5 toolkits">
</p>

<p align="center">
  <a href="#dr-features">Features</a> &nbsp;·&nbsp;
  <a href="#dr-quick-start">Quick Start</a> &nbsp;·&nbsp;
  <a href="#dr-datasets">Datasets</a> &nbsp;·&nbsp;
  <a href="#dr-documentation">Documentation</a> &nbsp;·&nbsp;
  <a href="README_zh.md">简体中文</a>
</p>

---

<a id="dr-overview"></a>

## What is DataReady?

**DataReady** brings together five independent, open-source workflow engines for preparing, improving, evaluating, and generating data for AI. It helps data engineers and researchers turn documents, media, and structured records into usable datasets for model development and downstream applications.

Each toolkit is an independent Python project with its own command-line entry point. **YAML workflows** define inputs, outputs, processing steps, and operator parameters; **custom Python operators** extend the built-in capabilities. Runs produce structured results, metrics, and reports, with checkpoint and resume support.

Use one toolkit for a focused task or connect several through files, mapping each toolkit's output fields to the next toolkit's input configuration.

<a id="dr-toolkits"></a>

## Toolkits

| Toolkit | Data types | Command |
| --- | --- | --- |
| **[Multimodal Content Parsing](MultimodalParsing/README.md)**<br>`MultimodalParsing/` | PDF · Word · Excel · HTML · Image · Audio | `parse` |
| **[Intelligent Data Deduplication](DataDeduplication/README.md)**<br>`DataDeduplication/` | Text · Image · Audio | `dedup` |
| **[Multimodal Data Denoising](DataDenoising/README.md)**<br>`DataDenoising/` | Text · Image · Image–text · Video | `denoise` |
| **[Data Quality Evaluation](QualityEvaluation/README.md)**<br>`QualityEvaluation/` | Text · Image · Audio | `quality-eval` |
| **[High-Quality Data Synthesis](DataSynthesis/README.md)**<br>`DataSynthesis/` | Text · Image · Structured · Multimodal | `synthesis` |

<a id="dr-features"></a>

## Core Capabilities

### Multimodal Content Parsing

[MultimodalParsing](MultimodalParsing/README.md) converts PDF, Word, Excel, HTML, image, and audio inputs into structured JSONL artifacts. Its parsing workflows bring together content extraction, OCR or ASR integration, Markdown reconstruction, chunking, and quality assessment. Output records retain source information, extracted content, metrics, and issues, making them suitable for subsequent cleaning, indexing, and dataset preparation.

### Intelligent Data Deduplication

[DataDeduplication](DataDeduplication/README.md) identifies exact and near-duplicate text, image, and audio samples. Text processing includes normalization, hashing, SimHash, and MinHash LSH; image processing includes file and perceptual hashing and structural similarity; audio processing includes file and PCM hashing, fingerprints, and acoustic similarity. Optional embedding, reranking, and ASR stages extend these workflows. Results include duplicate groups, representative samples, kept and removed records, review candidates, and decision reports.

### All-Modal Intelligent Data Denoising

[DataDenoising](DataDenoising/README.md) cleans text, images, image-text pairs, and video, with automatic routing for mixed inputs. Text operations cover normalization, markup cleanup, repetition filtering, and sensitive information masking. Image and video workflows assess decoding, resolution, blur, exposure, noise, and other quality signals; image-text workflows check consistency between modalities. Configurable quality decisions route samples into keep, drop, or manual-review outputs.

### Data Quality Evaluation

[QualityEvaluation](QualityEvaluation/README.md) evaluates text, image, and audio datasets and reports sample-level issues alongside dataset-level summaries. Checks cover field completeness, text length and punctuation, duplicate content, image integrity and annotations, and audio format, sample rate, clipping, noise, and echo. The toolkit produces quality scores, issue distributions, mappings to national-standard quality dimensions, Markdown reports, operator traces, and error queues to support review and improvement.

### High-Quality Data Synthesis

[DataSynthesis](DataSynthesis/README.md) generates new samples from seed data, prompts, and schemas. Built-in workflows cover text generation, text and table question answering, synonym replacement, question augmentation, structured-record generation, image generation, and multimodal synthesis. Internal validation, diversity checks, quality gates, and retry logic help separate accepted samples from filtered or failed results. Generated data, metrics, workflow copies, and checkpoints provide a traceable record of each run.

> **External model setup:** OCR, ASR, embedding, vision, and generative-model capabilities require the corresponding backend and credentials. Consult the toolkit guides for integrations and input/output requirements.

<a id="dr-workflow"></a>

## Typical Workflow

```text
Raw data  → Parse      → Deduplicate → Denoise → Evaluate → Usable datasets
Seed data → Synthesize → Deduplicate / Denoise / Evaluate → Expanded datasets
```

Choose the steps and order for your data and intended use. Toolkits exchange files; each workflow defines its own input and output format.

<a id="dr-installation"></a>

## Installation

**Requirements:** Python `>=3.10`; `uv` is recommended. Video denoising also requires `ffmpeg` / `ffprobe`.

Each toolkit has its own environment. For the examples below, enter the relevant toolkit directory before using `uv run`.

<a id="dr-quick-start"></a>

## Quick Start

Start with **structured data synthesis without an external model service**. Run from the repository root:

```bash
cd DataSynthesis
uv sync
uv run synthesis validate -c workflows/structured_synthesis.yaml
uv run synthesis run -c workflows/structured_synthesis.yaml
uv run synthesis report -t runs/structured_synthesis
```

Results are written to `DataSynthesis/runs/structured_synthesis/`. See the [DataSynthesis guide](DataSynthesis/README.md) for input, output, and report details.

Explore the other entry points from their respective toolkit directories:

| Working directory | Help command |
| --- | --- |
| `MultimodalParsing/` | `uv run parse --help` |
| `DataDeduplication/` | `uv run dedup --help` |
| `DataDenoising/` | `uv run denoise --help` |
| `QualityEvaluation/` | `uv run quality-eval --help` |
| `DataSynthesis/` | `uv run synthesis --help` |

<a id="dr-datasets"></a>

## Public Datasets

We also release five **WutongWanxiang** datasets on the Huanxin community(https://aihuanxin.cn/#/). They cover cross-cultural language, Chinese cultural imagery, model safety, industry knowledge, and technology-domain speech. Counts and descriptions follow the publishers’ introductions; use each dataset page for details and access.

| Dataset | Scale | Focus |
| --- | --- | --- |
| [Southeast Asia Culture and Values Parallel Corpus](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-SoutheastAsia_CultureValue_Parallel_Corpus/type=org) | **180,000+** | Cross-cultural alignment |
| [Chinese Poetry and Image Multimodal Dataset](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Poetry_Image_Multimodal_Dataset/type=org?tab=intro) | **9,900+** | Poetry and visual expression |
| [Chinese Safety QA Dataset](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Safety_QA_Dataset/type=org) | **200,000+** | Model safety and alignment |
| [Energy Patent Dataset](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang_Energy_Patent_Dataset/type=org) | **90,000+** | Energy and low-carbon knowledge |
| [Technology Industry Synthetic Speech Multimodal Dataset](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Tech_Synthetic_Speech_Multimodal_Dataset/type=org) | **38,000+** | Technology-domain speech synthesis and recognition |

Expand for content and preparation details:

<details>
<summary><strong>Southeast Asia Culture and Values Parallel Corpus</strong></summary>

This corpus contains **180,000+ text records** focused on cross-cultural alignment in Southeast Asia. It presents country-specific perspectives on shared social and cultural topics, with Chinese and English as semantic anchors and additional regional languages selected for the countries involved. JSON records contain a multilingual `text` object and country, topic, and value-category metadata. The corpus is generated and translated with language models, then filtered and checked through manual sampling. It is intended for region-aware language models, content moderation, and cross-cultural dialogue. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-SoutheastAsia_CultureValue_Parallel_Corpus/type=org).

</details>

<details>
<summary><strong>Chinese Poetry and Image Multimodal Dataset</strong></summary>

This dataset contains **9,900+ classical Chinese poetry–illustration pairs**. Each record connects a poem with a detailed visual description and a generated illustration, together with title, dynasty, and author metadata. The descriptions translate poetic imagery into concrete scene elements, composition, artistic techniques, and atmosphere. The dataset supports text-to-image model fine-tuning and research on connecting classical literature with visual expression. Its production process includes automated image-text quality assessment and manual sampling. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Poetry_Image_Multimodal_Dataset/type=org?tab=intro).

</details>

<details>
<summary><strong>Chinese Safety QA Dataset</strong></summary>

This dataset contains **200,000+ Chinese question-and-answer records** for language model safety evaluation and alignment. Each JSON record includes a prompt, a response, an overall safety label, and eight risk-category labels covering personal harm, discrimination and bias, prohibited goods, fraud and theft, hate speech, false or misleading information, unethical behavior, and privacy violations. Both safe and unsafe examples are included. The publisher identifies supervised fine-tuning and reinforcement learning from human feedback as intended uses, and lists project-collected data and a portion of BeaverTails among its sources. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Safety_QA_Dataset/type=org).

</details>

<details>
<summary><strong>Energy Patent Dataset</strong></summary>

This dataset contains text from **90,000+ patents** in energy and low-carbon industries. Structured records include titles, abstracts, claims, full descriptions, publication and application identifiers and dates, inventors, applicants, and legal status. A `meta.field` label assigns records to a classification system with **14 industry categories**, spanning energy resources, environmental protection, clean energy, recycling, green infrastructure, and carbon management. The dataset is intended to supply specialized technical knowledge for domain-specific language model fine-tuning. Its preparation includes patent collection, industry labeling, text extraction, and completeness checks. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang_Energy_Patent_Dataset/type=org).

</details>

<details>
<summary><strong>Technology Industry Synthetic Speech Multimodal Dataset</strong></summary>

This dataset contains **38,000+ text–speech pairs** spanning information technology, fintech, smart transportation, and related technology sectors, with specialized terminology and company or organization names. Each JSON record links the spoken text in `audio_text` to an audio file in `audio_path`, while `meta` records speaker gender and ID, sample rate, bit depth, duration, and domain labels. Preparation combines industry-keyword collection, automated generation of domain-specific sentences, and multi-speaker speech synthesis. Audio uses a consistent sample rate and bit depth to support training speech synthesis and recognition models for technology-industry scenarios. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Tech_Synthetic_Speech_Multimodal_Dataset/type=org).

</details>

> **Dataset and software licenses are separate.** These datasets are distributed outside this repository; the linked pages specify **CC BY-NC 4.0**, while the software uses **MIT**. Map downloaded text, image, and metadata fields to the selected toolkit’s input configuration.

<a id="dr-documentation"></a>

## Documentation

| Toolkit | Usage guide | Development guide | Configuration |
| --- | --- | --- | --- |
| **MultimodalParsing** | [Usage](MultimodalParsing/README.md) | [Development](MultimodalParsing/README_dev.md) | [Workflow](MultimodalParsing/docs/Workflow配置说明.md) |
| **DataDeduplication** | [Usage](DataDeduplication/README.md) | [Development](DataDeduplication/README_dev.md) | [Workflow](DataDeduplication/docs/Workflow配置说明.md) |
| **DataDenoising** | [Usage](DataDenoising/README.md) | [Development](DataDenoising/README_dev.md) | [Workflow](DataDenoising/docs/Workflow配置说明.md) |
| **QualityEvaluation** | [Usage](QualityEvaluation/README.md) | [Development](QualityEvaluation/README_dev.md) | [Workflow](QualityEvaluation/docs/Workflow配置说明.md) |
| **DataSynthesis** | [Usage](DataSynthesis/README.md) | [Development](DataSynthesis/README_dev.md) | [Workflow](DataSynthesis/docs/Workflow配置说明.md) |

Workflow configuration references are currently in Chinese.

<a id="dr-license"></a>

## License and Copyright

This project is licensed under the **MIT License**. See [LICENSE](LICENSE).

Copyright © 2026 China Mobile Information Technology

---

<p align="center">
  <a href="#dr-top">Back to top</a>
</p>
