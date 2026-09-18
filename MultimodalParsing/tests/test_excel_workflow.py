from pathlib import Path

import pandas as pd

import parse_engine.operators  # noqa: F401
from parse_engine.models import DataItem
from parse_engine.operators.excel_parse.document import ExcelStructureExtractOperator
from parse_engine.runtime.config import load_workflow_config
from parse_engine.runtime.executor import WorkflowExecutor


def test_excel_structure_extract_operator_handles_multiple_sheet_shapes(tmp_path: Path) -> None:
    """Verify that the Excel operator handles empty, header-only, and multi-sheet cases.

    Business logic:
        1. Build an xlsx file containing an empty sheet, a header-only sheet, and a normal data sheet.
        2. Run the excel_structure_extract operator and inspect generated heading and table artifacts.
        3. Assert issue reporting and preservation of sheet names, structure, and cell text.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> callable(test_excel_structure_extract_operator_handles_multiple_sheet_shapes)
        True
    """
    excel_path = tmp_path / "demo.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame(columns=["姓名", "得分"]).to_excel(writer, sheet_name="表头页", index=False)
        pd.DataFrame({"姓名": ["Alice", "Bob"], "得分": [95, 88]}).to_excel(writer, sheet_name="数据页", index=False)
        pd.DataFrame().to_excel(writer, sheet_name="空表页", index=False, header=False)

    item = DataItem.from_path(excel_path)
    result = ExcelStructureExtractOperator({}).process(item)

    table_artifacts = [artifact for artifact in result.artifacts if artifact.type == "table"]
    heading_artifacts = [artifact for artifact in result.artifacts if artifact.type == "heading"]
    assert result.action == "parsed"
    assert result.metrics["sheet_count"] == 3
    assert result.metrics["non_empty_sheet_count"] == 2
    assert len(heading_artifacts) == 2
    assert len(table_artifacts) == 2
    assert any((artifact.text or "") == "表头页" for artifact in heading_artifacts)
    assert any(artifact.data["sheet_name"] == "表头页" and artifact.data["header_only"] for artifact in table_artifacts)
    assert any("Alice" in (artifact.text or "") for artifact in table_artifacts)
    assert any(issue["type"] == "empty_excel_sheet" and issue["sheet_name"] == "空表页" for issue in result.issues)


def test_excel_workflow_outputs_markdown_and_chunks(tmp_path: Path) -> None:
    """Verify that the Excel workflow outputs structured artifacts, Markdown, and chunks.

    Business logic:
        1. Create an xlsx file with two sheets in a temporary directory.
        2. Write a minimal Excel workflow configuration and execute the full workflow.
        3. Assert that outputs include Excel table, Markdown, markdown_chunk, and a report.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "excel" in "excel_parse"
        True
    """
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "runs"
    input_dir.mkdir()

    excel_path = input_dir / "demo.xlsx"
    with pd.ExcelWriter(excel_path) as writer:
        pd.DataFrame({"字段": ["name", "city"], "值": ["demo", "Shanghai"]}).to_excel(writer, sheet_name="配置", index=False)
        pd.DataFrame(columns=["列1", "列2"]).to_excel(writer, sheet_name="仅表头", index=False)

    config_path = tmp_path / "excel_parse.yaml"
    config_path.write_text(
        f"""
workflow:
  id: excel_test
  name: Excel test
input:
  type: file_dir
  path: {input_dir.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: excel_parse
    operator: excel_parse
    params:
      chunking:
        target_len: 80
""",
        encoding="utf-8",
    )

    config = load_workflow_config(config_path)
    run_dir = WorkflowExecutor(config, config_path).run()

    artifacts = (run_dir / "artifacts.jsonl").read_text(encoding="utf-8")
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "配置" in artifacts
    assert "markdown_chunk" in artifacts
    assert '"type":"markdown"' in artifacts or '"type": "markdown"' in artifacts
    assert "### 配置" in artifacts
    assert "Sheet 配置" not in artifacts
    assert "Content Parsing Report" in report
