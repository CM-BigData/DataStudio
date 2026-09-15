# 内容解析样例数据来源说明

本目录用于 `workflows/*_parse.yaml` 的公开样例输入。所有文件均来自可公开访问的数据源，未使用自生成数据。

| 路径 | 来源项目/数据集 | 来源 URL | 许可证/使用条款 | 加工方式 |
| --- | --- | --- | --- | --- |
| `pdf/html40.pdf` | W3C HTML 4.0 Recommendation | https://www.w3.org/TR/1998/REC-html40-19980424/html40.pdf | W3C Document License | 原样下载并重命名 |
| `pdf/mathml.pdf` | W3C MathML Recommendation | https://www.w3.org/TR/MathML/mathml.pdf | W3C Document License | 原样下载并重命名 |
| `word/blk-inner-content.docx` | python-docx test files | https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/blk-inner-content.docx | MIT License | 原样下载并重命名 |
| `excel/any_sheets.xlsx` | calamine test files | https://raw.githubusercontent.com/tafia/calamine/master/tests/any_sheets.xlsx | MIT License | 原样下载并重命名 |
| `excel/any_sheets.xls` | calamine test files | https://raw.githubusercontent.com/tafia/calamine/master/tests/any_sheets.xls | MIT License | 原样下载并重命名 |
| `html/cover.html` | W3C HTML 4.0 Recommendation | https://www.w3.org/TR/1998/REC-html40-19980424/cover.html | W3C Document License | 原样下载并重命名 |
| `image/300-dpi.png` | python-docx test files | https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/300-dpi.png | MIT License | 原样下载并重命名 |
| `image/300-dpi.jpg` | python-docx test files | https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/300-dpi.jpg | MIT License | 原样下载并重命名 |
| `audio/librispeech-dev-clean-0000.flac` | Mini LibriSpeech dev-clean-2 | https://www.openslr.org/resources/31/dev-clean-2.tar.gz | CC BY 4.0 | 从压缩包抽取 `LibriSpeech/dev-clean-2/5694/64038/5694-64038-0000.flac` 并重命名 |
| `audio/librispeech-dev-clean-0001.flac` | Mini LibriSpeech dev-clean-2 | https://www.openslr.org/resources/31/dev-clean-2.tar.gz | CC BY 4.0 | 从压缩包抽取 `LibriSpeech/dev-clean-2/5694/64038/5694-64038-0001.flac` 并重命名 |

## 备注

- `example_data/audio/` 保留可直接被解析 workflow 读取的 `.flac` 文件，不交付原始压缩包。
- W3C 文档需随交付保留来源链接和许可证说明。
- Mini LibriSpeech 基于 LibriSpeech 派生，使用时需保留 CC BY 4.0 署名信息。
