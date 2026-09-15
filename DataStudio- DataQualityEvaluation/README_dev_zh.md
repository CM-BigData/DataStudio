# DataStudio-NationalStandardDataQualityEvaluation

> English version: [README_dev.md](README_dev.md)
>
> 部署使用手册: [README_zh.md](README_zh.md)

DataStudio-NationalStandardDataQualityEvaluation 是一个基于 workflow 的轻量级数据质量评测工具，包名为 `quality-eval-workflow-engine`，命令入口为 `quality-eval`。当前实现面向文本和图像数据集，支持通过 YAML/JSON workflow 调用端到端算子，对样本进行结构、完整性、长度、异常字符、重复、图片格式、分辨率、清晰度、空白图、疑似 AI 生成图、标注 bbox 等质量检查，并输出样本级结果、汇总 JSON、Markdown 报告、算子追踪日志、checkpoint 和错误队列。

## 开发手册

### 项目结构

```text
DataStudio-NationalStandardDataQualityEvaluation/
├── pyproject.toml              # 包信息、依赖和 quality-eval 脚本入口
├── src/quality_eval/           # 命令行、runtime、schemas 和端到端算子
├── workflows/                  # 文本、CSV、图像和扩展示例 workflow
├── example_data/               # 公开文本和图像样例数据
├── real_data/                  # 真实评测样本子集，仅供本地扩展验证使用
├── src/quality_eval/schemas/   # 输入、输出和 workflow JSON Schema
├── tests/                      # 命令行、workflow、算子、追踪、续跑等测试
└── docs/                       # 文档目录，当前包含 Workflow 配置说明
```

### 验证链路

开发或接入自定义算子后，使用真实命令行按顺序验证注册、配置、执行和报告导出：

```bash
uv run quality-eval --help
uv run quality-eval validate-config -c workflows/text_dataset_eval.yaml
uv run quality-eval run -c workflows/text_dataset_eval.yaml --task-id local_text --output-dir outputs/local_text
uv run quality-eval export-report -t outputs/local_text/text_eval_summary.json -o outputs/local_text/text_eval_report.md
```

其中 `--help` 用于确认 CLI 入口可用，`validate-config` 用于确认 `custom_operators`、`steps[].operator` 和输入路径可用，`run` 用于生成样本结果、summary、report、logs、errors 和 checkpoint，`export-report` 用于验证已有 summary 可重新生成 Markdown 报告。

### 开发自定义算子

自定义算子用于把项目尚未内置的文本、图像、评分或治理规则接入同一套 workflow。接入时提供可被 workflow 加载的 Python 算子文件和最小验证样本，不需要改命令行入口。

#### 1. 生成算子模板

使用真实命令行生成模板，建议放在项目内 `plugins/` 目录，便于 workflow 用相对路径加载；该目录当前不是内置包目录，可作为自定义算子目录。

```bash
mkdir -p plugins
uv run quality-eval operator-template --type text --name my_text_quality --output plugins/my_text_quality.py
uv run quality-eval operator-template --type image --name my_image_quality --output plugins/my_image_quality.py
uv run quality-eval operator-template --type score --name my_dataset_score --output plugins/my_dataset_score.py
uv run quality-eval operator-template --type governor --name my_quality_governor --output plugins/my_quality_governor.py
```

`--name` 会写入模板类属性 `operator_name`，必须是 snake_case，例如 `my_text_quality`。workflow 中 `steps[].operator` 必须填写同一个值。

#### 2. 实现 BaseOperator

每个自定义算子文件至少提供一个继承 `quality_eval.operators.common.base.BaseOperator` 的类，并实现 `process(self, item)`。`BaseOperator` 提供：

| 成员 | 用法 |
|---|---|
| `operator_name` | 注册名，必须是 snake_case，供 `steps[].operator` 引用。 |
| `operator_version` | 版本号，会进入算子 trace/log。 |
| `self.config` | workflow、runtime、step、rules 合并后的配置。 |
| `self.rules` | `rules` 快捷入口，用于读取阈值、权重和开关。 |
| `setup(items, context)` | 可选，适合构建重复检测索引、全局统计或共享上下文。 |
| `process(item)` | 必填，处理单条标准样本并返回样本。 |
| `teardown()` | 可选，释放文件、模型或连接资源。 |
| `add_issue(item, code)` | 追加去重后的问题码。 |
| `metric(item, key, value)` | 写入样本级指标。 |

最小文本算子示例：

```python
from __future__ import annotations

from typing import Any

from quality_eval.operators.common.base import BaseOperator


class MyTextQualityOperator(BaseOperator):
    operator_name = "my_text_quality"
    operator_version = "1.0.0"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        text = str(item.get("payload", {}).get("text", ""))
        self.metric(item, "my_text_length", len(text))
        if len(text.strip()) < int(self.rules.get("my_min_length", 1)):
            self.add_issue(item, "my_text_too_short")
            item["action"] = "review"
        return item
```

项目 AGENTS 要求 Python 代码注释和 docstring 使用英文；本次 README 仅展示最小代码片段，实际自定义算子也应遵守该规则。

#### 3. 在 workflow 中加载并使用

`custom_operators` 支持 Python 文件路径或模块路径。相对路径按 workflow 文件所在目录解析，因此推荐把自定义算子放到 workflow 旁边的 `plugins/`，或使用绝对路径。

```yaml
workflow:
  id: custom_text_quality_eval
  task_type: text
input:
  type: raw_text
  text: 需要评测的一段文本
output:
  result_path: ./outputs/custom_result.jsonl
  summary_path: ./outputs/custom_summary.json
  report_path: ./outputs/custom_report.md
rules:
  my_min_length: 10
custom_operators:
  - ./plugins/my_text_quality.py
steps:
  - id: custom_text_quality
    operator: my_text_quality
```

接入后先运行：

```bash
uv run quality-eval validate-config -c workflows/custom_text_quality.yaml
uv run quality-eval run -c workflows/custom_text_quality.yaml --task-id custom_text_quality --output-dir outputs/custom_text_quality
```

#### 4. 文本、图像、评分、治理算子的职责边界

| 类型 | 推荐输入 | 推荐输出 |
|---|---|---|
| 文本算子 | `item["payload"]["text"]`、`meta.label`、`self.rules` | 写入文本长度、格式、字符、语义等 `metrics`，追加可解释 `issues`。 |
| 图像算子 | `item["payload"]["image_path"]`、图像 `meta`、标注信息 | 写入分辨率、格式、清晰度、空白、AIGC、bbox 等 `metrics` 和 `issues`。 |
| 评分算子 | 已有 `metrics`、`issues`、`score_weights` 或 `rules` | 写入 `score`、`level`，必要时写入评分分项 `metrics`。 |
| 治理算子 | 已有 `issues`、`score`、业务规则 | 写入 `action`、`suggestions`，例如 `keep`、`review`、`drop`。 |

问题码、指标和分数应保持可解释：`issues` 使用稳定、可聚合的短码；`metrics` 记录触发依据或关键数值；`score` 和 `level` 能从规则或指标解释；`suggestions` 给出下一步处理建议。

### 接入约定

- 统一使用 `quality-eval run -c <workflow> --task-id <workflow/task-id> --output-dir <workflow/output-dir>`，其中 `task-id` 必须稳定且可追踪。
- 自定义算子建议集中放在 `plugins/`，workflow 使用 `custom_operators` 显式声明，不依赖隐式导入。
- 输入 schema 不应被算子隐式改变；算子可以补充 `metrics`、`issues`、`score`、`level`、`action`、`suggestions` 和 `intermediate`，不要删除或重命名 `id`、`modality`、`source`、`payload`、`meta` 等核心字段。
- `steps[].operator` 只引用 `operator_name`，不要引用类名或文件名。
- 发布前至少准备最小样本：文本算子用 `raw_text` 或 1-3 行 JSONL/CSV，图像算子用 1-3 张图片和最小 `annotations.json`，评分/治理算子用能触发目标 `issues` 的样本。
- 最小验证必须包含 `validate-config`、一次 `run`、检查 `summary/report/logs` 三类输出，并确认 `logs/<task_id>_operators.jsonl` 中能看到自定义算子的 `operator` 和 `operator_version`。

### 路径安全约定

命令入口在参数解析阶段将文件系统参数转换为标准路径对象，`safe_path` 和 `safe_output_path` 使用标准路径解析处理配置内路径，再通过 `allowed_roots` 约束规范化结果。命令入口默认以当前工作目录为授权根。`run`、`validate-config`、`export-report` 和 `operator-template` 可重复传入 `--allow-root`，用于访问其他现有目录。输入归一化会通过执行器 resolver 处理记录内媒体路径，`image_folder` annotation 中的图片路径也使用同一边界；文件型 `custom_operators` 在导入前执行授权根检查，模块型扩展只应引用可信环境中的模块。`validate_task_id` 将任务 ID 约束为安全文件名组件并拒绝 Windows 保留设备名，checkpoint、日志和错误队列路径还会按各自目录执行二次边界检查。图文一致性远端模型必须配置不可变 `image_text_consistency_model_revision`，并以 `trust_remote_code=False` 加载。

### 测试

```bash
cd DataStudio-NationalStandardDataQualityEvaluation
uv run pytest
```

可按范围运行：

```bash
uv run pytest tests/test_text_eval.py
uv run pytest tests/test_image_eval.py
uv run pytest tests/test_framework.py
```

当前仓库包含用于命令行算子列表、workflow 配置校验、文本 JSONL/CSV 评测、图像评测、空白图检测、疑似 AIGC 检测、标点/特殊字符算子、自定义算子、追踪日志和断点续跑字段的测试文件；但当前直接执行 `uv run pytest` 会因 `clean_version/tests` 与根 `tests/` 的同名测试收集冲突而在 collection 阶段报错。

### 注意事项

- README 只描述当前代码中存在的命令、workflow、算子和文件，不包含尚未实现的服务端或交互式 UI。
- 公开示例验证优先使用仓库内现有 `example_data/`；`real_data/` 仅适合本地扩展验证，不应视为默认输入。
- workflow 中的相对路径解析有两级：先按 workflow 所在目录，再按项目根目录。
- `--workers` 会覆盖 workflow/runtime 中的并发配置；多线程只在 worker 数和待处理样本数都足够时启用。
- `--resume` 依赖已存在的结果文件和 checkpoint，建议复用同一个 `--task-id` 与输出目录。
