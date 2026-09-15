from __future__ import annotations

from parse_engine.models import Artifact, DataItem, SourceTrace


def normalize_heading_level(value: object) -> int:
    """规范化 Markdown 标题级别

    业务逻辑：
        1. 接受上游 artifact.data 中的 `heading_level`。
        2. 对缺失或非整数值回退到二级标题，兼容旧产物。
        3. 将标题级别限制在 1 到 6 之间，防止生成非法 Markdown。

    Args:
        value (object): 原始标题级别值。

    Returns:
        int: 合法的 Markdown 标题级别。

    Examples:
        >>> normalize_heading_level(3)
        3
        >>> normalize_heading_level(None)
        2
    """
    if not isinstance(value, int):
        return 2
    return min(max(value, 1), 6)


def table_to_markdown(rows: list[list[str]]) -> list[str]:
    """将二维表数据转换为 Markdown 表格行

    业务逻辑：
        1. 对空表直接返回空列表。
        2. 根据最长行补齐列数，保证 Markdown 表头和数据行列宽一致。
        3. 使用首行作为表头，自动生成分隔行并拼接正文行。

    Args:
        rows (list[list[str]]): 二维表格内容，首行视为表头。

    Returns:
        list[str]: 逐行 Markdown 表格文本。

    Examples:
        >>> table_to_markdown([["field", "value"], ["name", "demo"]])[1]
        '| --- | --- |'
    """
    if not rows:
        return []
    width = max(len(row) for row in rows)
    padded = [row + [""] * (width - len(row)) for row in rows]
    header = padded[0]
    separator = ["---"] * width
    body = padded[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return lines


class MarkdownArtifactRebuilder:
    def rebuild_markdown(self, item: DataItem) -> str:
        """把现有 artifacts 重建为 Markdown 文本

        业务逻辑：
            1. 按现有 artifact 顺序遍历，保持上游结构顺序稳定。
            2. 将 heading、table 和普通文本分别转换成 Markdown 片段。
            3. 用空行拼接所有非空片段并返回最终 Markdown。

        Args:
            item (DataItem): 已包含解析 artifacts 的数据项。

        Returns:
            str: 重建后的 Markdown 文本。

        Examples:
            >>> item = DataItem(id="demo", source={"path": "demo.docx"}, payload={})
            >>> item.artifacts.append(Artifact(id="h", type="heading", text="Title", data={"heading_level": 1}))
            >>> MarkdownArtifactRebuilder().rebuild_markdown(item)
            '# Title'
        """
        parts: list[str] = []
        for artifact in item.artifacts:
            if artifact.type == "heading" and artifact.text:
                heading_level = normalize_heading_level(artifact.data.get("heading_level"))
                parts.append(f"{'#' * heading_level} {artifact.text}")
            elif artifact.type == "table" and artifact.data.get("rows"):
                rows = artifact.data["rows"]
                parts.extend(table_to_markdown(rows))
            elif artifact.text:
                parts.append(artifact.text)
        return "\n\n".join(part for part in parts if part)

    def build_markdown_artifact(self, item: DataItem, markdown: str, operator_name: str) -> Artifact:
        """根据 Markdown 文本构造统一的 markdown artifact

        业务逻辑：
            1. 复用当前数据项 id 和来源路径生成稳定 artifact 标识。
            2. 记录重建时的 artifact 数量，便于排查上下游产物差异。
            3. 使用调用方提供的 operator 名称写入 source_trace。

        Args:
            item (DataItem): 当前数据项。
            markdown (str): 已重建完成的 Markdown 文本。
            operator_name (str): 写入 source_trace 的 operator 名称。

        Returns:
            Artifact: 下游可直接复用的 markdown artifact。

        Examples:
            >>> item = DataItem(id="demo", source={"path": "demo.docx"}, payload={})
            >>> MarkdownArtifactRebuilder().build_markdown_artifact(item, "content", "markdown_rebuild").type
            'markdown'
        """
        return Artifact(
            id=f"{item.id}_markdown",
            type="markdown",
            text=markdown,
            data={"artifact_count": len(item.artifacts)},
            source_trace=SourceTrace(file=item.source["path"], operator=operator_name),
        )
