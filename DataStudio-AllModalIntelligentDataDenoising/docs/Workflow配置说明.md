# Workflow 配置说明

正式入口：`workflows/denoise_auto.yaml`

该 workflow 使用 JSON 写法保存为 `.yaml` 文件。JSON 是 YAML 的合法子集，也可以改写为普通 YAML。

## 顶层字段

| 字段 | 说明 |
| --- | --- |
| `workflow` | 流程元信息，包括 `id`、`mode`、`batch_size`、`concurrency`、`checkpoint` |
| `input` | 输入文件配置，正式入口默认 `../example_data/input.jsonl` |
| `output` | 输出目录和文件名，正式入口默认 `../outputs/latest` |
| `steps` | 端到端算子执行列表；主 workflow 只配置一个 step |

## 端到端算子

正式 workflow 使用单 step：

```json
"steps": [
  {
    "id": "auto_denoise",
    "operator": "auto_denoise",
    "params": {
      "profile": "default",
      "thresholds": {},
      "model_ref": {}
    }
  }
]
```

`auto_denoise` 内部执行输入防泄露、模态路由、各模态去噪流程和质量门控。中间环节不在 workflow `steps` 中暴露。

路由规则：

| 输入 payload | 模块 |
| --- | --- |
| `text` | 文本去噪 |
| `image_path` | 图片去噪 |
| `text + image_path` | 图文对去噪 |
| `video_path` | 视频去噪 |

## 正式运行命令

```powershell
python -m denoise_workflow_engine.cli.main validate -c workflows\denoise_auto.yaml
python -m denoise_workflow_engine.cli.main run -c workflows\denoise_auto.yaml
python -m denoise_workflow_engine.cli.main report -t outputs\latest
```

## 输出文件

```text
 outputs/latest/
  clean.jsonl
  dropped.jsonl
  review.jsonl
  metrics.json
  operator_logs.jsonl
  report.md
```

## 路径授权

`denoise validate` 和 `denoise run` 默认以当前工作目录作为授权根。命令行中的 workflow 配置和 `--allow-root` 在参数解析阶段转换为标准路径对象；workflow 中的输入路径、记录内文件字段、文件型 `custom_operators` 和 `output.run_dir` 随后执行真实路径规范化和授权根边界检查。使用可重复的 `--allow-root <directory>` 可授权其他现有目录。修复产物与视频中间文件位于本次 `output.run_dir` 或显式授权目录内，样本 ID 在用于文件名和中间目录前会校验为安全组件。`output.clean_path`、`output.dropped_path`、`output.review_path` 和 `output.report_path` 必须位于规范化后的 `output.run_dir` 内。

远端模型接口地址必须使用 `http` 或 `https` 协议并包含有效主机名。文本、视觉和音频客户端会在发起请求前校验由 `*_API_BASE` 与 endpoint path 组成的最终地址。

## 防泄露

正式 workflow 不需要 `manifest` 或任何预期标签。输入中如果出现 `expected_action`、`expected_clean`、`expected_file`、`manifest`、`ground_truth` 等字段，会在端到端算子内部标记为 `data_leakage_suspected`。

公开主入口为 `workflows/denoise_auto.yaml`。项目同时提供辅助验证与回归 workflow，用于公开样例复现和定向能力回归。
