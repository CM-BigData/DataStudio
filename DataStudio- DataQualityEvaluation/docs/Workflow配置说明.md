# Workflow 配置说明

Workflow 配置支持 YAML / JSON，MVP 示例位于 `workflows/`。

| 配置段 | 说明 |
|---|---|
| workflow | workflow id、名称、任务类型、并发、batch 和 checkpoint 开关 |
| input | 输入类型和输入路径；文本支持 jsonl / csv，图像为目录加 annotations.json |
| output | 样本级 JSONL、汇总 JSON 和 Markdown 报告路径 |
| rules | 质量规则阈值和算子参数 |
| runtime | 执行器类型、worker 数和 batch_size |
| score_weights | 国标维度综合评分权重；暂未启用维度会自动跳过并归一化 |
| steps | 串行 Pipeline 步骤，operator 字段对应公开端到端算子注册名 |

相对路径会优先按配置文件所在目录解析；如不存在，再按工程根目录解析。命令默认以当前工作目录作为授权根，使用可重复的 `--allow-root <directory>` 可授权其他现有目录。命令行路径参数在参数解析阶段转换为标准路径对象，配置内路径随后执行真实路径规范化和授权根边界检查。规范化后的配置、输入、输出、记录内媒体路径、图片 annotation 路径和文件型 `custom_operators` 必须位于授权根内。`--task-id` 只接受字母、数字、点、下划线和连字符并拒绝 Windows 保留设备名，派生的 checkpoint、日志和错误队列文件必须位于各自输出目录内。图文一致性使用远端模型时，`rules.image_text_consistency_model_revision` 必须配置为经过审核的不可变提交哈希，加载过程不执行远端自定义代码。

公开示例 workflow 默认从 `example_data/` 读取可分发的小样本数据；`real_data/` 和 `real_reports/` 仅用于真实数据验证，不属于公开快速开始路径。

## 端到端算子步骤

`steps` 中只引用公开端到端算子；单项检查通过 `params.enabled_checks` 控制，不能直接引用内部中间步骤。

```yaml
workflow:
  task_type: text

steps:
  - id: text_dataset_eval
    operator: text_dataset_eval
    params:
      enabled_checks:
        - special_characters
        - punctuation_pairing
```

未配置 `enabled_checks` 时，端到端算子会运行该模态的完整内部检查链路。
