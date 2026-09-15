# Content Parsing Example Data Sources

This directory provides public sample inputs for `workflows/*_parse.yaml`. All files come from publicly accessible sources. No self-generated data is used.

| Path | Source project/dataset | Source URL | License/terms | Processing |
| --- | --- | --- | --- | --- |
| `pdf/html40.pdf` | W3C HTML 4.0 Recommendation | https://www.w3.org/TR/1998/REC-html40-19980424/html40.pdf | W3C Document License | Downloaded as-is and renamed |
| `pdf/mathml.pdf` | W3C MathML Recommendation | https://www.w3.org/TR/MathML/mathml.pdf | W3C Document License | Downloaded as-is and renamed |
| `word/blk-inner-content.docx` | python-docx test files | https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/blk-inner-content.docx | MIT License | Downloaded as-is and renamed |
| `excel/any_sheets.xlsx` | calamine test files | https://raw.githubusercontent.com/tafia/calamine/master/tests/any_sheets.xlsx | MIT License | Downloaded as-is and renamed |
| `excel/any_sheets.xls` | calamine test files | https://raw.githubusercontent.com/tafia/calamine/master/tests/any_sheets.xls | MIT License | Downloaded as-is and renamed |
| `html/cover.html` | W3C HTML 4.0 Recommendation | https://www.w3.org/TR/1998/REC-html40-19980424/cover.html | W3C Document License | Downloaded as-is and renamed |
| `image/300-dpi.png` | python-docx test files | https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/300-dpi.png | MIT License | Downloaded as-is and renamed |
| `image/300-dpi.jpg` | python-docx test files | https://raw.githubusercontent.com/python-openxml/python-docx/master/tests/test_files/300-dpi.jpg | MIT License | Downloaded as-is and renamed |
| `audio/librispeech-dev-clean-0000.flac` | Mini LibriSpeech dev-clean-2 | https://www.openslr.org/resources/31/dev-clean-2.tar.gz | CC BY 4.0 | Extracted `LibriSpeech/dev-clean-2/5694/64038/5694-64038-0000.flac` from the archive and renamed |
| `audio/librispeech-dev-clean-0001.flac` | Mini LibriSpeech dev-clean-2 | https://www.openslr.org/resources/31/dev-clean-2.tar.gz | CC BY 4.0 | Extracted `LibriSpeech/dev-clean-2/5694/64038/5694-64038-0001.flac` from the archive and renamed |

## Notes

- `example_data/audio/` keeps directly readable `.flac` files for the parsing workflow. The original archive is not included.
- Keep source links and W3C license information with redistributed W3C documents.
- Mini LibriSpeech is derived from LibriSpeech. Keep CC BY 4.0 attribution information when redistributing it.
