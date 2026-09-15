# DataStudio-IntelligentDataDeduplication

> English version: [README.md](README.md)
>
> 开发手册: [README_dev_zh.md](README_dev_zh.md)

DataStudio-IntelligentDataDeduplication 是一个面向文本、图片、音频样本的数据去重工作流引擎。项目包名为 `dedup-workflow-engine`，命令行入口为 `dedup`，可以通过 YAML 工作流配置运行端到端去重能力；归一化、候选召回、相似度融合、重复簇聚合、保留样本选择和报告输出均由端到端算子内部完成。

项目当前公开 `text_dedup`、`image_dedup`、`audio_dedup` 三个端到端算子，分别支持文本、图像和音频数据的智能化去重。

## 部署使用手册

### 核心能力

- 文本端到端去重：`text_dedup` 内部完成文本归一化、精确哈希、SimHash、MinHash LSH、可选 embedding、可选 rerank、重复边融合、聚类和保留样本选择。
- 图片端到端去重：`image_dedup` 内部完成图片路径解析、文件哈希、感知哈希、结构相似度、可选图片 embedding、可选目标区域相似度、融合、聚类和保留样本选择。
- 音频端到端去重：`audio_dedup` 内部完成音频路径解析、文件哈希、PCM 哈希、能量指纹、声学特征相似度、可选音频 embedding、可选 ASR、融合、聚类和保留样本选择。
- 工作流执行：主工作流使用单个端到端 operator step。
- 自动路由：`auto-run` 可读取混合 JSONL 输入，按 `text`、`image`、`audio` 分桶并选择对应工作流。
- 可追踪输出：每次运行会生成保留样本、移除样本、待复核样本、重复簇、指标、算子日志、Markdown 报告和 checkpoint。
- 工具目录边界：向量、文本/图片/音频共享算法、纯文本归一化函数等纯工具统一放入 `src/dedup_workflow_engine/utilities/`；各模态端到端业务编排统一放在 `src/dedup_workflow_engine/operators/*_dedup/pipeline.py`，`operators/` 保留端到端算子和仍具 workflow 身份的内部 stage。
- 扩展算子：支持通过 `custom_operators` 加载外部 Python 算子文件，也可用 `operator-template` 生成模板。
- 样本检查：支持按重复簇 ID 或样本 ID 查看运行输出和关联决策。

### 安装与环境

#### 依赖要求

- Python >= 3.10
- 运行依赖：`PyYAML`、`Pillow`（图片处理）
- 推荐使用 `uv` 运行命令，仓库已包含 `uv.lock`

#### 本地安装

```bash
cd DataStudio-IntelligentDataDeduplication
uv sync
```

`uv sync` 会安装全部运行依赖，包括图片处理所需的 `Pillow`。

#### 直接调用命令

如果 `dedup` 已安装到系统 `PATH`，可直接调用：

```bash
dedup --help
```

Windows PowerShell 中如未识别 `dedup`，可先激活项目虚拟环境后再调用：

```powershell
.\.venv\Scripts\Activate.ps1
dedup --help
```

#### 外部模型环境变量

默认示例工作流可以在不配置外部服务的情况下运行。需要启用 embedding、rerank、ASR 或自定义 JSON 服务时，参考 `configs/api_env.template.ps1` 和 `configs/model_registry.yaml` 设置环境变量，例如：

```powershell
$env:TEXT_RERANK_API_BASE = "https://coding.dashscope.aliyuncs.com/v1"
$env:TEXT_RERANK_MODEL = "qwen3.6-plus"
$env:TEXT_RERANK_API_KEY = "<put-your-api-key-in-current-shell-only>"
```

命令行启动时会尝试从当前目录加载 `configs/api_env.local.ps1`，该本地文件不应提交真实密钥。

### 快速开始

#### 1. 校验工作流配置

```bash
uv run dedup validate -c workflows/text_dedup_strict.yaml
```

成功时输出：

```text
workflow config is valid
```

#### 2. 运行文本去重工作流

```bash
uv run dedup run -c workflows/text_dedup_strict.yaml
```

运行后会在 `runs/text_strict/` 下生成输出。公开示例 workflow 默认读取 `example_data/` 下的小型可分发样例数据，用于环境自检和功能演示。

#### 3. 查看运行报告

```bash
sed -n '1,80p' runs/text_strict/report.md
```

报告包含工作流 ID、样本计数、重复边数量、移除率、耗时、问题分布、重复簇预览和输出文件说明。

#### 4. 查看重复簇或样本

```bash
uv run dedup inspect-group --group-id dup_group_000001 --run-dir runs/text_strict
uv run dedup inspect-item --item-id txt_001 --run-dir runs/text_strict --input example_data/text/input.jsonl
```

### 命令行用法

顶层命令：

```bash
uv run dedup --help
```

支持的子命令如下：

| 命令 | 用途 |
| --- | --- |
| `dedup run -c CONFIG [--resume]` | 执行一个 YAML 工作流配置。 |
| `dedup auto-run --input INPUT --output-dir OUTPUT_DIR [--workflow-dir workflows] [--profile strict|basic] [--modality auto|text|image|audio] [--resume]` | 读取混合 JSONL，按模态路由并分别运行匹配工作流。 |
| `dedup validate -c CONFIG` | 校验工作流必需字段、输入配置和端到端算子可创建性。 |
| `dedup operator-template --type text|image|audio --name NAME --output OUTPUT` | 生成可加载的自定义端到端算子模板。 |
| `dedup inspect-group --group-id GROUP_ID [--run-dir RUN_DIR]` | 查看重复簇 JSON；未指定 `run_dir` 时从 `runs/*/duplicate_groups.jsonl` 按更新时间查找。 |
| `dedup inspect-item --item-id ITEM_ID --run-dir RUN_DIR [--input INPUT] [--max-text-chars N] [--verbose]` | 查看样本输入、输出动作和关联重复簇。 |

可通过模块方式运行同一入口：

```bash
uv run python -m dedup_workflow_engine.cli.main validate -c workflows/text_dedup_strict.yaml
uv run python -m dedup_workflow_engine run -c workflows/text_dedup_strict.yaml
```

### 输入与输出

#### 输入格式

标准输入项 schema 位于 `src/dedup_workflow_engine/schemas/input_schema.json`。每条样本至少包含：

```json
{
  "id": "sample_001",
  "modality": "text",
  "payload": {
    "text": "需要去重的文本"
  },
  "meta": {}
}
```

支持的 `modality` 为 `text`、`image`、`audio`。对应 payload 常用字段：

| 模态 | payload 字段 |
| --- | --- |
| `text` | `text` |
| `image` | `image_path` |
| `audio` | `audio_path` |

工作流输入配置还支持 `auto`、`jsonl`、`json`、`csv`、`directory`、`file`、`stdin`、`raw_text` 类型，并可通过 `id_field`、`modality_field`、`text_field`、`image_path_field`、`audio_path_field` 映射字段。

仓库内置公开示例输入：

- `example_data/text/input.jsonl`
- `example_data/image/input.jsonl`
- `example_data/audio/input.jsonl`

#### 工作流配置

工作流 schema 位于 `src/dedup_workflow_engine/schemas/workflow_schema.json`。一个工作流至少包含 `workflow`、`input`、`output`、`steps`：

```yaml
workflow:
  id: text_dedup_strict_v1
  name: Strict text deduplication workflow
  modality: text
  mode: pipeline
  checkpoint: true

input:
  type: jsonl
  path: ./example_data/text/input.jsonl

output:
  run_dir: ./runs/text_strict

steps:
  - id: text_dedup
    operator: text_dedup
    params:
      profile: strict
      methods:
        exact_hash: true
        simhash:
          bit_size: 64
          ngram: 2
          max_hamming_distance: 10
        minhash:
          shingle_size: 5
          min_length: 35
          jaccard_threshold: 0.55
        embedding: false
        rerank: false
      thresholds:
        cluster_min_score: 0.55
```

内置工作流位于 `workflows/`，包括文本、图片、音频基础版与严格版。公开运行主路径默认使用这些读取 `example_data/` 的 workflow。

#### 输出文件

标准输出项 schema 位于 `src/dedup_workflow_engine/schemas/output_schema.json`。每条最终样本至少包含 `id`、`modality`、`action`，其中 `action` 为 `keep`、`remove` 或 `review`。

每个 run 目录通常包含：

| 文件 | 说明 |
| --- | --- |
| `kept.jsonl` | 最终保留样本。 |
| `removed.jsonl` | 因重复簇选择了其他代表样本而移除的样本。 |
| `review.jsonl` | 需要人工复核的样本。 |
| `duplicate_groups.jsonl` | 重复簇、成员、保留/移除决策、原因和分数。 |
| `metrics.json` | 工作流级指标、耗时、吞吐、checkpoint 和处理计数。 |
| `operator_logs.jsonl` | 算子级执行日志。 |
| `report.md` | Markdown 汇总报告。 |
| `checkpoints/` | 开启 checkpoint 时的步骤快照。 |

### 运行去重 workflow

主路径是“准备输入 -> 校验配置 -> 运行 -> 检查输出”：

```bash
uv run dedup validate -c workflows/text_dedup_strict.yaml
uv run dedup run -c workflows/text_dedup_strict.yaml
uv run dedup inspect-group --group-id dup_group_000001 --run-dir runs/text_strict
uv run dedup inspect-item --item-id txt_001 --run-dir runs/text_strict --input example_data/text/input.jsonl
```

混合模态输入走 `auto-run`，工具会按 `modality` 或 `payload.text`、`payload.image_path`、`payload.audio_path` 识别 `text`、`image`、`audio`，再按 profile 选择工作流：

```bash
uv run dedup auto-run --input data/mixed/input.jsonl --output-dir runs/mixed_auto --workflow-dir workflows --profile strict
```

`auto-run --profile basic` 查找 `workflows/{modality}_dedup.yaml`，`strict` 查找 `workflows/{modality}_dedup_strict.yaml`。需要干净重跑时使用新的 `output.run_dir` 或清理对应 run 目录；`--resume` 会开启 checkpoint 并尝试复用已成功步骤。

### 路径授权

`scripts/build_manifest.py` 默认只访问当前工作目录下的输入和输出路径。处理其他目录时，使用可重复的 `--allow-root <directory>` 显式授权现有目录。命令行路径参数在参数解析阶段转换为标准路径对象，随后执行真实路径规范化和授权根边界检查。规范化后的路径必须位于当前工作目录或授权目录内。目录遍历得到的每个文件都会按真实路径再次校验，符号链接或 junction 指向授权根外时会拒绝生成清单。

```bash
uv run python scripts/build_manifest.py --text-dir D:/datasets/texts --output data/input.jsonl --allow-root D:/datasets
```

### 注意事项

- 不要把真实 API Key 写入或提交到仓库；优先使用当前 shell 环境变量或本地 `configs/api_env.local.ps1`。
- 默认严格工作流中的外部 embedding、rerank、ASR 内部 stage 多为 `enabled: false`；启用前需要确认服务地址、模型名、密钥和输入字段。
- 图片工作流读取 `image_path`，音频工作流读取 `audio_path`；相对路径按运行目录和输入适配逻辑解析，建议在项目根目录运行示例命令。
- `--resume` 会开启 checkpoint 并尝试复用已有输出；需要干净重跑时先使用新的 `output.run_dir` 或清理对应 run 目录。
- `auto-run --profile basic` 会查找 `workflows/{modality}_dedup.yaml`，`strict` 会查找 `workflows/{modality}_dedup_strict.yaml`。
- 自定义端到端算子应继承 `dedup_workflow_engine.operators.base.BaseOperator`，设置唯一 `operator_name`，并在工作流的 `custom_operators` 中声明文件路径。

### 版权与许可证

- 本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。
