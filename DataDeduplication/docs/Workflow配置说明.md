# Workflow 配置说明

每个 workflow 由四部分组成：

| 配置块 | 说明 |
| --- | --- |
| workflow | 流程 ID、模态、执行模式、checkpoint 开关 |
| input | 输入类型和输入路径 |
| output | run 目录和输出文件名 |
| steps | 算子步骤列表；pipeline 按顺序执行，dag 按依赖计划执行 |

示例：

```yaml
workflow:
  id: text_dedup_demo
  modality: text
  mode: pipeline
  checkpoint: true

input:
  type: jsonl
  path: ./example_data/text/input.jsonl

output:
  run_dir: ./runs/text_demo

steps:
  - id: text_normalize
    operator: text_normalize_for_dedup
    params:
      lowercase: true
```

## DAG 配置

如果 workflow 需要表达分支依赖，可设置 `mode: dag` 并在 step 上声明 `depends_on`：

```yaml
workflow:
  id: example_dag
  modality: text
  mode: dag
  checkpoint: true

steps:
  - id: normalize
    operator: text_normalize_for_dedup
    params: {}
  - id: exact_hash
    operator: exact_hash_deduplicator
    depends_on: normalize
    params: {}
  - id: simhash
    operator: simhash_deduplicator
    depends_on: normalize
    params: {}
  - id: cluster
    operator: duplicate_cluster
    depends_on:
      - exact_hash
      - simhash
    params: {}
```

当前执行器会按 DAG 依赖顺序生成执行计划。若配置 `runtime.executor: process`、`runtime.workers > 1`、`runtime.allow_parallel_steps: true`，同一 DAG level 中互不依赖且 `parallel_safe` 不为 `false` 的步骤会使用多进程并行执行。

并行步骤的输出、checkpoint 和日志仍由主进程按 workflow step 顺序确定性合并和写入，避免多个进程同时写结果文件造成不可复现。示例配置见 `workflows/text_dedup_parallel_dag.yaml`。

```yaml
runtime:
  executor: process
  workers: 2
  allow_parallel_steps: true

steps:
  - id: exact_hash
    operator: exact_hash_deduplicator
    depends_on: text_normalize
    parallel_safe: true
    params: {}
  - id: simhash
    operator: simhash_deduplicator
    depends_on: text_normalize
    parallel_safe: true
    params: {}
```

说明：当前并行能力针对 DAG 独立步骤；默认 strict workflow 仍使用串行 pipeline，以保证直接运行时结果稳定。算子内部的超大规模 pairwise 并行属于后续性能压测优化项。

去重流程会在 `context.duplicate_edges` 中累计重复关系，再由 `duplicate_cluster` 聚类成 `duplicate_groups`。

## 路径授权

`scripts/build_manifest.py` 默认只访问当前工作目录内的输入目录、输出文件和相对路径基准。使用可重复的 `--allow-root <directory>` 可授权其他现有目录。命令行路径参数在参数解析阶段转换为标准路径对象，所有路径会在访问前完成真实路径规范化和授权根边界检查。目录遍历得到的每个文件会按真实路径再次校验，符号链接或 junction 不得指向授权根外。
