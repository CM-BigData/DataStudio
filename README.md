# DataStudio

> 中文版本: [README_zh.md](README_zh.md)

DataStudio is an open-source collection of workflow engines for preparing, improving, evaluating, and generating data for AI applications. It brings together five complementary capabilities: multimodal content parsing, intelligent deduplication, data denoising, data quality evaluation, and high-quality data synthesis. Together, these tools help data engineers and researchers turn documents, media, and structured records into usable datasets for model development and downstream applications.

Each toolkit is an independent Python project with its own command-line entry point. YAML workflows describe inputs, outputs, processing steps, and operator parameters; custom Python operators allow teams to extend the built-in capabilities. Runs produce structured results, metrics, and reports, with checkpoint and resume support for longer jobs. Users can run one toolkit for a focused task or combine several through file-based workflows, adapting output fields to the next toolkit's input configuration.

A typical data preparation process starts by extracting content, removing duplicate and low-quality samples, and evaluating the resulting dataset. Synthesis workflows can then generate additional text, image, structured, or multimodal samples, which can be reviewed with the same cleaning and evaluation tools. The order and selection of steps depend on the source data and the intended use.

## Toolkits

The repository root contains the following toolkit directories:

| Directory | Command | Purpose |
| --- | --- | --- |
| `DataStudio-MultimodalContentParsing/` | `parse` | Parses PDF, Word, Excel, HTML, images, audio, and other content |
| `DataStudio-IntelligentDataDeduplication/` | `dedup` | Deduplicates text, image, and audio samples |
| `DataStudio-AllModalIntelligentDataDenoising/` | `denoise` | Cleans and routes text, images, image-text pairs, video, and other data |
| `DataStudio-DataQualityEvaluation/` | `quality-eval` | Checks the quality of text, image, and audio datasets |
| `DataStudio-HighQualityDataSynthesis/` | `synthesis` | Runs text, image, structured, and multimodal data synthesis workflows |

## Core Capabilities

### Multimodal Content Parsing

[DataStudio-MultimodalContentParsing](DataStudio-MultimodalContentParsing/README.md) converts PDF, Word, Excel, HTML, image, and audio inputs into structured JSONL artifacts. Its parsing workflows bring together content extraction, OCR or ASR integration, Markdown reconstruction, chunking, and quality assessment. Output records retain source information, extracted content, metrics, and issues, making them suitable for subsequent cleaning, indexing, and dataset preparation.

### Intelligent Data Deduplication

[DataStudio-IntelligentDataDeduplication](DataStudio-IntelligentDataDeduplication/README.md) identifies exact and near-duplicate text, image, and audio samples. Text processing includes normalization, hashing, SimHash, and MinHash LSH; image processing includes file and perceptual hashing and structural similarity; audio processing includes file and PCM hashing, fingerprints, and acoustic similarity. Optional embedding, reranking, and ASR stages extend these workflows. Results include duplicate groups, representative samples, kept and removed records, review candidates, and decision reports.

### All-Modal Intelligent Data Denoising

[DataStudio-AllModalIntelligentDataDenoising](DataStudio-AllModalIntelligentDataDenoising/README.md) cleans text, images, image-text pairs, and video, with automatic routing for mixed inputs. Text operations cover normalization, markup cleanup, repetition filtering, and sensitive information masking. Image and video workflows assess decoding, resolution, blur, exposure, noise, and other quality signals; image-text workflows check consistency between modalities. Configurable quality decisions route samples into keep, drop, or manual-review outputs.

### Data Quality Evaluation

[DataStudio-DataQualityEvaluation](DataStudio-DataQualityEvaluation/README.md) evaluates text, image, and audio datasets and reports sample-level issues alongside dataset-level summaries. Checks cover field completeness, text length and punctuation, duplicate content, image integrity and annotations, and audio format, sample rate, clipping, noise, and echo. The toolkit produces quality scores, issue distributions, mappings to national-standard quality dimensions, Markdown reports, operator traces, and error queues to support review and improvement.

### High-Quality Data Synthesis

[DataStudio-HighQualityDataSynthesis](DataStudio-HighQualityDataSynthesis/README.md) generates new samples from seed data, prompts, and schemas. Built-in workflows cover text generation, text and table question answering, synonym replacement, question augmentation, structured-record generation, image generation, and multimodal synthesis. Internal validation, diversity checks, quality gates, and retry logic help separate accepted samples from filtered or failed results. Generated data, metrics, workflow copies, and checkpoints provide a traceable record of each run.

Capabilities that use external OCR, ASR, embedding, vision, or generative models require the corresponding backend and credentials to be configured. Each toolkit's guide describes its local workflows, optional integrations, and input and output requirements.

## Public Datasets

The WutongWanxiang datasets below are published by JIUTIAN on the Huanxin community. They cover cross-cultural language data, Chinese cultural imagery, model safety, and industry knowledge. The summaries and record counts below follow the publishers' dataset introductions; each link provides the full dataset description and access information.

### Southeast Asia Culture and Values Parallel Corpus

This corpus contains **180,000+ text records** focused on cross-cultural alignment in Southeast Asia. It presents country-specific perspectives on shared social and cultural topics, with Chinese and English as semantic anchors and additional regional languages selected for the countries involved. JSON records contain a multilingual `text` object and country, topic, and value-category metadata. The corpus is generated and translated with language models, then filtered and checked through manual sampling. It is intended for region-aware language models, content moderation, and cross-cultural dialogue. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-SoutheastAsia_CultureValue_Parallel_Corpus/type=org).

### Chinese Poetry and Image Multimodal Dataset

This dataset contains **9,900+ classical Chinese poetry–illustration pairs**. Each record connects a poem with a detailed visual description and a generated illustration, together with title, dynasty, and author metadata. The descriptions translate poetic imagery into concrete scene elements, composition, artistic techniques, and atmosphere. The dataset supports text-to-image model fine-tuning and research on connecting classical literature with visual expression. Its production process includes automated image-text quality assessment and manual sampling. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Poetry_Image_Multimodal_Dataset/type=org?tab=intro).

### Chinese Safety QA Dataset

This dataset contains **200,000+ Chinese question-and-answer records** for language model safety evaluation and alignment. Each JSON record includes a prompt, a response, an overall safety label, and eight risk-category labels covering personal harm, discrimination and bias, prohibited goods, fraud and theft, hate speech, false or misleading information, unethical behavior, and privacy violations. Both safe and unsafe examples are included. The publisher identifies supervised fine-tuning and reinforcement learning from human feedback as intended uses, and lists project-collected data and a portion of BeaverTails among its sources. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang-Chinese_Safety_QA_Dataset/type=org).

### Energy Patent Dataset

This dataset contains text from **90,000+ patents** in energy and low-carbon industries. Structured records include titles, abstracts, claims, full descriptions, publication and application identifiers and dates, inventors, applicants, and legal status. A `meta.field` label assigns records to a classification system with **14 industry categories**, spanning energy resources, environmental protection, clean energy, recycling, green infrastructure, and carbon management. The dataset is intended to supply specialized technical knowledge for domain-specific language model fine-tuning. Its preparation includes patent collection, industry labeling, text extraction, and completeness checks. [Dataset details](https://aihuanxin.cn/dataset/detail/JIUTIAN/WutongWanxiang_Energy_Patent_Dataset/type=org).

These datasets are distributed separately from this repository. Each linked dataset page specifies **CC BY-NC 4.0**; DataStudio's **MIT** license applies to the software. To process downloaded records, map their text, image, or metadata fields to the selected toolkit's input configuration and consult that toolkit's guide for the required format.

## Requirements

- Python `>=3.10`
- `uv` is recommended

## Installation

Run the following commands in order from the repository root:

```bash
cd DataStudio-MultimodalContentParsing && uv sync && cd ..
cd DataStudio-IntelligentDataDeduplication && uv sync && cd ..
cd DataStudio-AllModalIntelligentDataDenoising && uv sync && cd ..
cd DataStudio-DataQualityEvaluation && uv sync && cd ..
cd DataStudio-HighQualityDataSynthesis && uv sync && cd ..
```

Using `uv` directly is also recommended in Windows PowerShell. To invoke a command-line entry point directly, first enter the corresponding toolkit directory and activate `.venv`.

## Quick Start

First, confirm that all five command-line entry points are available:

```bash
cd DataStudio-MultimodalContentParsing && uv run parse --help && cd ..
cd DataStudio-IntelligentDataDeduplication && uv run dedup --help && cd ..
cd DataStudio-AllModalIntelligentDataDenoising && uv run denoise --help && cd ..
cd DataStudio-DataQualityEvaluation && uv run quality-eval --help && cd ..
cd DataStudio-HighQualityDataSynthesis && uv run synthesis --help && cd ..
```

Then enter the toolkit directory you need and run the corresponding workflow. Each toolkit's `README.md` provides complete workflow examples, input and output descriptions, and environment variable configuration.

## Toolkit Documentation

- [DataStudio-MultimodalContentParsing](DataStudio-MultimodalContentParsing/README.md)
- [DataStudio-IntelligentDataDeduplication](DataStudio-IntelligentDataDeduplication/README.md)
- [DataStudio-AllModalIntelligentDataDenoising](DataStudio-AllModalIntelligentDataDenoising/README.md)
- [DataStudio-DataQualityEvaluation](DataStudio-DataQualityEvaluation/README.md)
- [DataStudio-HighQualityDataSynthesis](DataStudio-HighQualityDataSynthesis/README.md)

## License and Copyright

License: MIT

Copyright © 2026 China Mobile Information Technology
