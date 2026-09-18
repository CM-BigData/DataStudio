from pathlib import Path

import parse_engine.operators  # noqa: F401

from parse_engine.models import DataItem
from parse_engine.operators.html_parse.document import HtmlBodyExtractOperator
from parse_engine.runtime.config import load_workflow_config
from parse_engine.runtime.executor import WorkflowExecutor


def test_html_body_extract_operator_reads_normal_html(tmp_path: Path) -> None:
    """Verify that the HTML operator extracts headings, paragraphs, and tables.

    Business logic:
        1. Write an HTML file containing a heading, paragraph, and table in a temporary directory.
        2. Pass it to html_body_extract through DataItem.from_path.
        3. Assert heading, paragraph, and table artifacts are generated and marked parsed.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "heading" in "heading"
        True
    """
    html_path = tmp_path / "demo.html"
    html_path.write_text(
        """
<html>
  <body>
    <h1>测试标题</h1>
    <p>第一段正文。</p>
    <table>
      <tr><th>字段</th><th>值</th></tr>
      <tr><td>name</td><td>demo</td></tr>
    </table>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    item = DataItem.from_path(html_path)
    result = HtmlBodyExtractOperator({}).process(item)

    artifact_types = [artifact.type for artifact in result.artifacts]
    assert result.action == "parsed"
    assert "heading" in artifact_types
    assert "paragraph" in artifact_types
    assert "table" in artifact_types
    assert any(artifact.text == "测试标题" for artifact in result.artifacts if artifact.type == "heading")


def test_html_body_extract_operator_handles_empty_html(tmp_path: Path) -> None:
    """Verify that the HTML operator handles empty HTML.

    Business logic:
        1. Write an empty HTML file.
        2. Execute html_body_extract.
        3. Assert the sample fails, has no artifacts, and records an empty_html_document issue.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "" == ""
        True
    """
    html_path = tmp_path / "empty.html"
    html_path.write_text("", encoding="utf-8")

    item = DataItem.from_path(html_path)
    result = HtmlBodyExtractOperator({}).process(item)

    assert result.action == "failed"
    assert result.artifacts == []
    assert result.issues[0]["type"] == "empty_html_document"


def test_html_body_extract_operator_filters_noise_tags(tmp_path: Path) -> None:
    """Verify that the HTML operator filters common noise tags.

    Business logic:
        1. Build HTML containing script, style, nav, and body paragraph content.
        2. Execute html_body_extract.
        3. Assert output contains body text and excludes navigation and script text.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "body" in "body"
        True
    """
    html_path = tmp_path / "noise.html"
    html_path.write_text(
        """
<html>
  <body>
    <style>.hidden{display:none;}</style>
    <script>console.log("noise")</script>
    <nav>首页 | 导航</nav>
    <p>保留的正文内容。</p>
  </body>
</html>
""".strip(),
        encoding="utf-8",
    )

    item = DataItem.from_path(html_path)
    result = HtmlBodyExtractOperator({}).process(item)
    texts = " ".join(artifact.text or "" for artifact in result.artifacts)

    assert "保留的正文内容。" in texts
    assert "首页" not in texts
    assert "noise" not in texts


def test_html_workflow_outputs_markdown_and_chunks(tmp_path: Path) -> None:
    """Verify that the HTML workflow completes the Markdown and chunk pipeline.

    Business logic:
        1. Write an HTML file with a heading and body text, then generate a minimal workflow config.
        2. Execute the end-to-end html_parse workflow.
        3. Assert artifacts.jsonl contains Markdown and markdown_chunk results.

    Args:
        tmp_path (Path): Temporary directory provided by pytest.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "markdown" in "markdown_chunk"
        True
    """
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "runs"
    input_dir.mkdir()
    (input_dir / "demo.html").write_text(
        """
<html><body><h1>HTML 标题</h1><p>用于工作流验证的正文段落。</p></body></html>
""".strip(),
        encoding="utf-8",
    )

    config_path = tmp_path / "html_parse.yaml"
    config_path.write_text(
        f"""
workflow:
  id: html_test
  name: HTML test
input:
  type: file_dir
  path: {input_dir.as_posix()}
output:
  type: jsonl
  path: {output_dir.as_posix()}
steps:
  - id: html_parse
    operator: html_parse
    params:
      chunking:
        target_len: 40
""",
        encoding="utf-8",
    )

    config = load_workflow_config(config_path)
    run_dir = WorkflowExecutor(config, config_path).run()

    artifacts = (run_dir / "artifacts.jsonl").read_text(encoding="utf-8")
    assert "html_body_extract" in artifacts
    assert "\"type\":\"markdown\"" in artifacts
    assert "\"type\":\"markdown_chunk\"" in artifacts
