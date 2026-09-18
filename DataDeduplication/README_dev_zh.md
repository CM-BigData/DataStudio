<a id="dr-top"></a>

<p align="center">
  <img src="../asset/wutong-data-color.svg" height="52" alt="梧桐数据 / Wutong Data">
  <img src="../asset/divider-vertical.png" height="42" alt="">
  <img src="../asset/jiutian-intelligent-color.svg" height="52" alt="九天智能 / Jiutian Intelligence">
</p>

<h1 align="center">DataDeduplication</h1>

<p align="center">
  <strong>DataReady · 智能数据去重</strong><br>
  开发指南 · 识别重复样本，保留有代表性的数据。
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB.svg" alt="Python 3.10+">
  <a href="../LICENSE"><img src="https://img.shields.io/badge/License-MIT-16a34a.svg" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/CLI-dedup-0284c7.svg" alt="CLI: dedup">
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
- [开发流程](#dr-开发流程)
- [接入约定](#dr-接入约定)
- [接入与排障流程](#dr-接入与排障流程)
- [测试](#dr-testing)
- [辅助脚本](#dr-辅助脚本)
- [相关文档](#dr-documentation)

</details>

<a id="dr-overview"></a>

## 模块简介

DataDeduplication 是一个面向文本、图片、音频样本的数据去重工作流引擎。项目包名为 `dedup-workflow-engine`，命令行入口为 `dedup`，可以通过 YAML 工作流配置运行端到端去重能力；归一化、候选召回、相似度融合、重复簇聚合、保留样本选择和报告输出均由端到端算子内部完成。

项目当前公开 `text_dedup`、`image_dedup`、`audio_dedup` 三个端到端算子。内部仍保留本地规则、特征计算、embedding、rerank、ASR 等 stage，但它们不再作为 workflow 可直接引用的公开算子。

| 命令入口 | 示例工作流 | 数据类型 |
| --- | --- | --- |
| `dedup` | [`text_dedup.yaml`](workflows/text_dedup.yaml) | 文本 · 图片 · 音频 |

<a id="dr-project-structure"></a>

## 项目结构

```text
DataDeduplication/
├── pyproject.toml                         # 包元数据、依赖和 dedup 命令入口
├── configs/                               # 运行时与外部模型服务配置模板
├── example_data/                          # 公开的小型示例输入与标注
├── docs/                                  # 文档目录，当前包含 Workflow 配置说明
├── data/                                  # 内部验证与历史样例数据
├── runs/                                  # 示例运行输出
├── src/dedup_workflow_engine/
│   ├── cli/                               # argparse命令行入口
│   ├── operators/                         # 端到端算子入口、workflow-facing stage 与公共后处理能力
│   ├── utilities/                         # 纯工具与共享算法 helper
│   ├── runtime/                           # 配置加载、输入适配、注册表、调度、执行、报告
│   └── schemas/                           # 输入、输出和工作流 JSON Schema
├── tests/                                 # 单元测试与 command-line/工作流烟测
└── workflows/                             # 可运行 YAML 工作流
```

主要内置端到端算子名可直接用于 `steps[].operator`：

- `text_dedup`
- `image_dedup`
- `audio_dedup`

当前内置模态目录结构约定如下：

- `text_dedup/operator.py` 只保留 workflow 入口类，`text_dedup/pipeline.py` 负责文本端到端编排。
- `image_dedup/operator.py` 只保留 workflow 入口类，`image_dedup/pipeline.py` 负责图片端到端编排。
- `audio_dedup/operator.py` 只保留 workflow 入口类，`audio_dedup/pipeline.py` 负责音频端到端编排。
- `operators/common/` 只放跨模态复用的后处理与基础能力，不放某个模态专属的端到端编排。

<a id="dr-custom-operators"></a>

## 开发自定义算子

本节说明如何扩展去重能力。常规运行只需要准备输入 JSONL 或目录，选择 `workflows/` 中的工作流，然后执行 `validate`、`run` 或 `auto-run`；自定义开发则需要提供可被 workflow 加载的端到端算子、最小样本和可验证配置。

<a id="dr-开发流程"></a>

## 开发流程

自定义端到端算子必须继承 `dedup_workflow_engine.operators.base.BaseOperator`，设置唯一的 snake_case `operator_name`，并在 workflow 顶层 `custom_operators` 中声明 Python 文件路径。建议把外部插件统一放在 `workflows/plugins/`，例如 `workflows/plugins/my_text_dedup.py`，避免混入内置 `src/dedup_workflow_engine/operators/`。

用模板生成起点：

```bash
mkdir -p workflows/plugins
uv run dedup operator-template --type text --name my_text_dedup --output workflows/plugins/my_text_dedup.py
```

可选模板类型为 `text`、`image`、`audio`。生成文件会包含 `BaseOperator`、`operator_name`、`process_dataset` 输入输出约定和 workflow 示例；开发时应把归一化、召回、融合、聚类和选择等内部逻辑封装在一个端到端算子内。

最小可加载 workflow 示例：

```yaml
workflow:
  id: custom_text_dedup
  modality: text
input:
  type: raw_text
  text: demo
output:
  run_dir: ./runs/custom_text
custom_operators:
  - ./plugins/my_text_dedup.py
steps:
  - id: my_text_dedup
    operator: my_text_dedup
    params:
      profile: basic
      threshold: 0.9
```

`steps[].operator` 必须等于端到端算子类的 `operator_name`。`steps[].params` 会作为 `self.config` 传入算子，适合放 `profile`、`methods`、`thresholds`、`model_ref` 等端到端配置。`validate` 会加载 `custom_operators` 并实例化每个 step，因此能提前发现文件不存在、`operator_name` 拼写错误、重复注册、输入路径不存在和未知 `input.type`。

<a id="dr-接入约定"></a>

## 接入约定

- 路径解析：`dedup run -c path/to/workflow.yaml` 中的 `custom_operators` 相对路径按 workflow 文件所在目录解析；如果插件放在 `workflows/plugins/`，则 workflow 中应写 `./plugins/<name>.py`。`input.path`、`output.run_dir` 和样本内相对 `image_path`、`audio_path` 按当前命令运行目录解析。建议从项目根目录运行命令，或在配置中使用绝对路径。
- 输入字段：标准样本包含 `id`、`modality`、`payload`、`meta`；文本读取 `payload.text`，图片读取 `payload.image_path`，音频读取 `payload.audio_path`。输入适配器也支持 `id_field`、`modality_field`、`text_field`、`image_path_field`、`audio_path_field` 映射 CSV/JSON 字段。
- 输出字段：端到端算子不要删除 `id`、`modality`、`payload`、`meta`、`intermediate`、`metrics`、`issues`、`action`。内部临时结果可写入 `intermediate`，调试或质量分写入 `metrics`，可解释问题写入 `issues`，重复候选边写入 `context["duplicate_edges"]`。
- 外部服务：embedding、rerank、ASR 和自定义 JSON 服务默认可关闭。启用前需要在端到端 step 的 `params.methods` 或 `params.model_ref` 中配置开关，并在当前 shell 或 `configs/api_env.local.ps1` 中配置对应的 `*_API_BASE`、`*_API_KEY`、`*_MODEL`。
- 最小样本验证：发布前至少提供 2 到 5 条能触发目标逻辑的 JSONL 或 `raw_text` 样本，先运行 `uv run dedup validate -c <workflow>`，再运行 `uv run dedup run -c <workflow>`，最后用 `inspect-group`、`inspect-item` 和 `operator_logs.jsonl` 证明端到端算子已被调用且输出符合预期。

<a id="dr-接入与排障流程"></a>

## 接入与排障流程

1. 生成模板并确认名称：`operator-template --name my_operator` 只接受 snake_case，workflow 中使用 `operator: my_operator`。
2. 把文件加入 `custom_operators`：相对路径以 workflow 文件目录为基准；找不到文件时 `validate` 会报 `Custom operator file not found`。
3. 校验 workflow：`uv run dedup validate -c <workflow>`；如果出现 `Unknown operator`，检查 `operator_name`、`steps[].operator` 和是否声明了 `custom_operators`。
4. 运行最小样本：先用 `raw_text`、小 JSONL 或 2 到 5 个媒体文件验证单一端到端算子，再接入完整 strict workflow。
5. 检查结果：看 `runs/<name>/operator_logs.jsonl` 的 `step_id`、`operator`、`status`，用 `inspect-group` 查重复簇，用 `inspect-item --verbose` 查单条样本的 `intermediate`、`metrics`、`issues` 和最终 `action`。
6. 处理外部服务问题：当启用服务但环境变量缺失或服务失败时，样本会出现如 `text_embedding_api_not_configured`、`text_rerank_api_not_configured`、`image_embedding_api_failed`、`audio_embedding_api_failed`、`asr_api_not_configured`、`asr_api_failed` 等 issue；先确认 `enabled`、环境变量、endpoint、模型名、密钥和返回字段。

<a id="dr-testing"></a>

## 测试

运行全部测试：

```bash
uv run pytest
```

按测试面向的能力划分：

- `tests/test_runtime.py`：工作流执行、输出文件、指标和报告。
- `tests/test_text_rules.py`：文本内部归一化、精确哈希、SimHash、MinHash 工具函数。
- `tests/test_parallel_executor.py`：DAG 同层并行执行与 checkpoint。
- `tests/test_router.py`：模态识别与自动路由。
- `tests/test_flexible_input_custom_operator.py`：灵活输入、CSV/JSON/raw text、自定义算子和模板生成。
- `tests/test_build_manifest.py`：目录扫描生成 manifest。
- `tests/test_env_loader.py`：本地 PowerShell 环境变量加载。
- `tests/test_rerank_edges.py`：rerank 候选边去重合并。

<a id="dr-辅助脚本"></a>

## 辅助脚本

- `scripts/build_manifest.py`：扫描 `texts`、`images`、`audios` 等目录并生成统一 `input.jsonl`，方便把目录数据接入 `dedup auto-run` 或其他 workflow。
- `--text-dir` 既支持 `.txt/.md` 原始文本文件，也支持 `.jsonl/.json/.csv` 文本清单；结构化记录会优先读取 `payload.text`，其次读取 `text`、`content`、`body`，没有文本字段的记录会跳过。
- 示例：

```bash
uv run python scripts/build_manifest.py \
  --text-dir data/texts \
  --image-dir data/images \
  --audio-dir data/audios \
  --output data/input.jsonl
```

脚本在参数解析阶段将输入目录、输出文件、`--relative-base` 和 `--allow-root` 转换为标准路径对象，随后对这些路径及目录遍历得到的每个文件执行真实路径规范化和授权根边界检查。默认授权根为当前工作目录；访问其他现有目录时可重复传入 `--allow-root <directory>`。符号链接或 junction 解析到授权根外时会直接拒绝。

<a id="dr-documentation"></a>

## 相关文档

- [使用指南](README_zh.md) · [开发指南](README_dev_zh.md)
- [Workflow 配置说明](docs/Workflow配置说明.md) · [示例工作流](workflows/)
- [示例数据来源](example_data/SOURCES.md) · [第三方依赖许可证清单](docs/第三方依赖许可证清单.md)

---

<p align="center">
  <a href="#dr-top">返回顶部</a> &nbsp;·&nbsp; <a href="../README_zh.md">DataReady 首页</a>
</p>
