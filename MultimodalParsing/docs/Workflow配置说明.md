# Workflow 配置说明

一个 workflow 由四部分组成：

```yaml
workflow:
  id: pdf_parse_v1
  name: PDF 内容解析流程
  mode: pipeline
  batch_size: 8
  concurrency: 1
  checkpoint: true

input:
  type: file_dir
  path: example_data/pdf

output:
  type: jsonl
  path: runs/pdf_parse
  report_path: runs/pdf_parse/report.md

steps:
  - id: pdf_parse
    operator: pdf_parse
    params:
      document_parse:
        provider: openai_compatible
        model: gpt-5.5
        api_key_env: OPENAI_API_KEY
        api_base_env: OPENAI_BASE_URL
        max_pages: 32
```

- `workflow`：流程元信息。
- `input`：输入类型和路径。完整输入类型以 `README_zh.md` 为准，当前实现支持单文件、目录、JSON、JSONL、CSV、raw_text 和 stdin。
- `output`：输出目录，每次运行会直接写入该目录。
- `steps`：公开端到端算子列表。当前内置 workflow 每种格式只配置一个端到端算子。

当前公开内置算子为 `pdf_parse`、`word_parse`、`excel_parse`、`html_parse`、`image_parse`、`audio_parse`。抽取、OCR、ASR、Markdown 重建、Markdown 分块和质量评估都由端到端算子内部编排，不再作为 workflow YAML 的公开 step 暴露。

`pdf_parse` 与 `image_parse` 的文档解析参数应直接写在 workflow 的 `params.document_parse` 中。默认 provider 为 `openai_compatible`，也支持切换成 `ocrflux`。OCRFlux 跨页元素合并响应会执行安全字面量解析、索引对类型校验和页面范围校验。

`word_parse` 对 `.doc` 或伪 `docx` 的转换命令路径应写在 workflow 的 `params.structure.soffice_command` 与 `params.media.soffice_command` 中。

音频 workflow 使用 `audio_parse`。ASR backend 通过 `steps[].params.asr` 显式声明，未启用或未配置时会记录 `asr_not_configured` issue，不会写入伪造 transcript。

例如：

```yaml
steps:
  - id: audio_parse
    operator: audio_parse
    params:
      asr:
        provider: dashscope_qwen_asr
        enabled: true
        model: qwen3-asr-flash
        api_key_env: DASHSCOPE_API_KEY
```

运行：

```bash
uv run parse validate -c workflows/pdf_parse.yaml
uv run parse run -c workflows/pdf_parse.yaml
uv run parse trace -t runs/pdf_parse --sample-id demo_page_1_text
```
