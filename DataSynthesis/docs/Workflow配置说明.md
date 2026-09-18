# Workflow 配置说明

数据合成 workflow 必须只声明一个端到端算子步骤。生成、校验、多样性、安全和质量门控等中间环节通过端到端算子的 `params.stages` 配置，不作为 `steps[].operator` 直接出现。

```yaml
workflow:
  id: text_synthesis_v1
  name: 文本数据合成流程
  retry_limit: 1
input:
  type: seed_yaml
  path: example_data/text/text_topics.yaml
output:
  type: jsonl
  path: runs/text_synthesis
steps:
  - id: text_synthesis
    operator: text_synthesis
    params:
      stages:
        text_llm_synthesis:
          model_ref: text_generation
          prompt_template: instruction_generation
          response_format: json
        text_format_validate:
          min_length: 50
        diversity_score: {}
        safety_filter:
          banned_words: [password, secret]
        quality_gate:
          pass_score: 0.7
          retry_limit: 1
```

运行：

```bash
synthesis validate -c workflows/text_synthesis.yaml
synthesis run -c workflows/text_synthesis.yaml
synthesis report -t runs/text_synthesis
synthesis trace -t runs/text_synthesis --sample-id text_quality_rules
```

`params` 白名单为 `profile`、`model_ref`、`generation`、`validation`、`quality` 和 `stages`。其中 `stages` 只配置内部阶段参数，不改变公开 operator 边界。

模型配置通过环境变量引用端点和凭据，例如：

```yaml
model_config:
  provider: openai
  model: gpt-4.1-mini
  api_base_env: LLM_API_BASE
  api_key_env: LLM_API_KEY
```

携带 API 密钥访问远程 OpenAI-compatible 服务时，端点必须使用 HTTPS。HTTP 仅允许连接 `localhost`、`127.0.0.1` 或 `::1` 上的本地兼容服务。
