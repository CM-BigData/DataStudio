# DataStudio-AllModalIntelligentDataDenoising

> English version: [README_dev.md](README_dev.md)
>
> 部署使用手册: [README_zh.md](README_zh.md)

DataStudio-AllModalIntelligentDataDenoising 是一个面向多模态数据清洗与质量路由的轻量工作流引擎。项目提供 `denoise` 命令行入口，可按配置读取文本、图片、图文对、视频等输入，执行内置或自定义去噪算子，并将样本分流到保留、剔除、人工复核三类输出。

项目包名为 `denoise-workflow-engine`，Python 包路径为 `denoise_workflow_engine`，默认正式 workflow 为 `workflows/denoise_auto.yaml`。

## 开发手册

### 开发自定义算子

#### 运行与算子开发边界

常规运行只需要准备输入、选择 workflow 并执行 `validate -> run -> report`：

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
uv run denoise run -c workflows/denoise_auto.yaml
uv run denoise report -t outputs/latest
```

自定义算子需要把完整的数据集处理能力封装成 `BaseOperator` 子类，声明唯一的端到端 `operator_name`，通过 `custom_operators` 接入 workflow，并把算子作为 workflow 的单 step 执行。随后仍使用同一套 `validate -> run -> report` 命令执行，不需要修改命令行代码。

#### 生成模板

推荐先用真实命令行生成模板，再在模板的 `process` 方法中填入业务逻辑：

```bash
mkdir -p workflows/plugins
uv run denoise operator-template --type text_denoise --name my_text_denoise --output workflows/plugins/my_text_denoise.py
uv run denoise operator-template --type image_denoise --name my_image_denoise --output workflows/plugins/my_image_denoise.py
uv run denoise operator-template --type video_denoise --name my_video_denoise --output workflows/plugins/my_video_denoise.py
uv run denoise operator-template --type image_text_pair_denoise --name my_pair_denoise --output workflows/plugins/my_pair_denoise.py
uv run denoise operator-template --type auto_denoise --name my_auto_denoise --output workflows/plugins/my_auto_denoise.py
```

`--type` 可选 `text_denoise`、`image_denoise`、`video_denoise`、`image_text_pair_denoise`、`auto_denoise`。`--name` 必须是 snake_case，并且会成为 workflow `steps[].operator` 使用的注册名。

#### BaseOperator 契约

自定义算子文件必须提供至少一个继承自 `denoise_workflow_engine.operators.base.BaseOperator` 的类：

```python
from __future__ import annotations

from typing import Any

from denoise_workflow_engine.operators.base import BaseOperator


class MyTextFilterOperator(BaseOperator):
    operator_name = "my_text_filter"
    operator_version = "1.0.0"

    def process(self, item: dict[str, Any]) -> dict[str, Any]:
        text = str(item.get("payload", {}).get("text", ""))
        if "advertisement" in text.lower():
            self.add_issue(item, "custom_advertisement")
            self.set_metric(item, "custom_advertisement_hit", True)
            item["action"] = "drop"
        return item
```

核心约定：

- `operator_name` 必须唯一，不能与内置算子重复；重复名称会在 registry 构建时失败。
- `operator_name` 必须是 snake_case，首字符为字母，只使用小写字母、数字和下划线。
- `process(item)` 输入和返回同一个 DataItem 字典，保留 `id`、`payload`、`meta`、`metrics`、`issues`、`operator_trace` 等核心字段。
- 使用 `self.add_issue(item, "issue_name")` 写入问题标签，标签会进入 `issues` 和 `metrics.json` 的 `issue_distribution`。
- 使用 `self.set_metric(item, "metric_name", value)` 写入证据指标，指标会随样本进入 `clean.jsonl`、`dropped.jsonl` 或 `review.jsonl`。
- 可写入 `item["quality_score"]` 或 `metrics["quality_score"]`，供端到端算子内部质量门控按 `keep_score`、`review_score` 和 `hard_fail_issues` 决定 `keep`、`drop`、`review`。
- 可写入 `item["intermediate"]` 存放 OCR、ASR、关键帧、模型响应等内部证据，供同一个端到端算子内部流程读取。
- 抛出的异常会被执行器捕获，样本会追加 `operator_failed` 并进入 `review`。

#### 各类型端到端算子开发重点

文本端到端算子读取 `payload.text`，内部可执行规范化、敏感信息治理、低质过滤、语义评分和质量门控。

图片端到端算子读取 `payload.image_path`，内部可执行解码、分辨率、清晰度、曝光、噪声、水印、Logo、安全、修复和质量门控。

视频端到端算子读取 `payload.video_path`，内部可执行探测、解码、关键帧、音频、字幕 OCR、ASR、AIGC、音画一致性、修复和质量门控。

图文对端到端算子读取 `payload.text` 和 `payload.image_path`，内部可执行结构完整性、OCR 文本一致性、关键词/CLIP/VLM 一致性、安全融合和质量门控。

自动端到端算子读取文本、图片、图文对或视频输入，内部完成模态路由并调用对应处理流程。

#### 在 workflow 中启用

建议把自定义算子统一放在 `workflows/plugins/`，例如 `workflows/plugins/my_text_denoise.py`。`custom_operators`、`input.path` 和 `output.run_dir` 中的相对路径都按 workflow 文件所在目录解析；因此 workflow 中应写 `./plugins/my_text_denoise.py`，它会指向 `workflows/plugins/my_text_denoise.py`。

最小接入示例：

```yaml
custom_operators:
  - ./plugins/my_text_denoise.py
steps:
  - id: my_text_denoise
    operator: my_text_denoise
    params:
      profile: default
      thresholds:
        keep_score: 0.75
        review_score: 0.55
```

`steps[].id` 是本次 workflow 节点 ID，`steps[].operator` 必须等于端到端算子类的 `operator_name`，`steps[].params` 会作为 `self.config` 传入算子实例。主 workflow 应只配置一个端到端 operator step；预处理、模型调用、评分和门控应在端到端算子内部编排。

#### 外部依赖启用前提

外部模型、OCR、ASR、CLIP、VLM 和视频工具不是命令行自动提供的能力，启用前需要满足对应前提：

- LLM/VLM/OCR/CLIP/ASR：在 `configs/api.env.example` 对应变量基础上配置 `*_API_KEY`、`*_API_BASE`、`*_MODEL` 和 endpoint path，并在算子 `params` 中引用对应环境变量名。
- 远端模型接口只接受包含有效主机名的 `http` 或 `https` 地址；文本、视觉和音频客户端会在发起请求前校验最终 endpoint。
- OCR/ASR：需要真实服务返回可解析的 OCR 文本或转写文本；不要在输入中预置 `precomputed_ocr_text`、`precomputed_asr_text` 作为答案提示。
- ffmpeg/ffprobe：视频探测、解码、关键帧、音频抽取和修复依赖系统 PATH 中可执行的 `ffmpeg` 和 `ffprobe`。
- 依赖不可用时，算子应写入明确的 `issues` 和 `metrics`，让端到端算子的内部质量门控或人工复核处理，而不是静默当作通过。

#### 最小样本验证

发布前，至少用小样本完成一次完整链路验证：

```bash
uv run denoise validate -c workflows/denoise_auto.yaml
uv run denoise run -c workflows/denoise_auto.yaml
uv run denoise report -t outputs/latest
```

验收重点：

- `validate` 输出 `workflow config is valid`，证明 `custom_operators` 可导入、`operator_name` 可注册、`steps` 可实例化。
- `run` 输出 `workflow_id`、`total`、`keep`、`drop`、`review`、`failed` 和 `report`。
- `outputs/latest/metrics.json` 中有总量、路由计数、失败计数、并发信息和 `issue_distribution`。
- `clean.jsonl`、`dropped.jsonl`、`review.jsonl` 中的样本包含 `issues`、`metrics`、`operator_trace`、`action` 和 `quality_score`。
- 自定义算子的关键证据必须能在样本级 `metrics` 或 `issues` 中看到；路由决策必须能由 `operator_trace`、`quality_score` 和端到端算子参数解释。

### 项目结构

```text
DataStudio-AllModalIntelligentDataDenoising/
├── pyproject.toml                         # 包元数据、依赖和 denoise 脚本入口
├── uv.lock                                # uv 锁文件
├── example_data/                          # 公开样例输入与资源
│   ├── input.jsonl                        # 公开主 workflow 默认读取的样例输入
│   └── assets/                            # 公开图片和视频样例资源
├── configs/
│   └── api.env.example                    # 外部模型 API 环境变量示例
├── workflows/                             # 正式 workflow 与辅助验证 workflow
│   ├── denoise_auto.yaml                  # 公开的正式自动路由 workflow
│   ├── local_real_smoke.yaml              # 公开样例 smoke workflow
│   ├── video_aigc_detect_smoke.yaml       # 视频 AIGC 检测 smoke workflow
│   └── ...                                # 其余公开验证与回归 workflow
├── docs/                                  # 文档目录，当前包含 Workflow 配置说明
├── tests/                                 # 单元测试、真实样本夹具和 workflow 验证
└── src/denoise_workflow_engine/
    ├── cli/main.py                        # 命令行子命令入口
    ├── __main__.py                        # python -m denoise_workflow_engine 入口
    ├── schemas/                           # 输入、输出、workflow JSON Schema
    ├── runtime/                           # workflow 加载、输入适配、执行、报告、注册表
    ├── utilities/                         # 纯工具目录：配置装配、stage 编排辅助、模态工具底座
    │   ├── config.py                      # workflow 配置到内部参数的装配工具
    │   ├── pipeline.py                    # 端到端内部 stage 执行与 trace 辅助
    │   ├── image/
    │   │   ├── base.py                    # 图片模态纯工具底座
    │   │   └── decode.py                  # 图片解码工具
    │   ├── text/
    │   │   └── base.py                    # 文本模态纯工具底座
    │   ├── video/
    │   │   └── base.py                    # 视频模态纯工具底座
    │   └── image_text_pair/
    │       └── base.py                    # 图文对纯工具底座
    └── operators/
        ├── __init__.py                    # 统一导出内置端到端算子
        ├── base.py                        # 算子基类
        ├── common/                        # 防泄露、路由、质量门等跨模态共享能力
        ├── text_denoising/                # 文本去噪实现目录
        │   ├── operator.py                # workflow 入口类
        │   ├── pipeline.py                # 端到端主编排
        │   ├── assessors/                 # 评测类能力
        │   ├── governors/                 # 治理与修复类能力
        │   └── pipelines/                 # 文本子流程
        ├── image_denoising/               # 图片去噪实现目录：operator.py + pipeline.py + 内部 stage
        ├── image_text_pair_denoising/     # 图文对去噪实现目录：operator.py + pipeline.py + 内部 stage
        ├── video_denoising/               # 视频去噪实现目录：operator.py + pipeline.py + 内部 stage
        └── auto_denoising/                # 自动路由去噪实现目录：operator.py + pipeline.py
```

当前内置端到端算子的结构约定如下：

- `operators/__init__.py` 负责统一导出 workflow 可注册的内置端到端算子。
- 每个模态目录内由 `operator.py` 提供 workflow 入口类，由 `pipeline.py` 负责该模态的端到端编排。
- 各模态内部复用的底座类、配置装配、路径解析和轻量 helper 统一收敛到 `utilities/`，避免把纯工具能力继续堆在 workflow 算子目录里。
- `operators/common/` 只放跨模态共享能力；具体模态能力继续留在各自 `*_denoising/` 目录中。

### 路径安全约定

命令入口在参数解析阶段将 workflow 配置和 `--allow-root` 转换为标准路径对象；输入路径、记录内文件字段、文件型 `custom_operators` 和 `output.run_dir` 通过标准路径解析进入同一授权根边界。默认授权根为当前工作目录；`--allow-root` 只接受现有目录并可重复传入。四个可配置输出文件会在打开前统一解析，并强制保留在规范化后的 `output.run_dir` 内；内部 stage 通过 `_runtime` 继承同一授权上下文，修复产物和视频中间文件使用受约束子路径。程序化调用 `resolve_path`、`InputAdapter` 和 `WorkflowExecutor` 时可传入 `allowed_roots` 启用同一边界。模块型自定义算子会执行 Python 导入逻辑，应只声明可信环境中的模块。

### 测试

推荐使用 `uv` 运行测试：

```bash
uv run pytest
```

可按范围运行：

```bash
uv run pytest tests/test_flexible_input_custom_operator.py
uv run pytest tests/test_text_sensitive_layers.py tests/test_text_mac_address_layers.py
uv run pytest tests/test_video_aigc_operator.py
```

现有测试覆盖：

- JSON、JSONL、CSV、目录、文件和 raw text 输入适配
- 自定义算子模板生成、加载、校验和执行
- workflow 相对路径解析、断点续跑、并发执行
- 文本敏感信息分层检测与脱敏
- MAC 地址真实文本样本回归
- 视频 AIGC 检测算子和真实样本 smoke workflow
- 通用路由、质量门和部分图片/图文对/视频算子行为
