from __future__ import annotations

from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.utilities.markdown.chunker import MarkdownChunker


class MarkdownChunkArtifactBuilder:
    def __init__(self, config: dict | None = None) -> None:
        """初始化 Markdown 分块产物构建器

        业务逻辑：
            1. 接收 operator 透传的分块配置。
            2. 统一创建底层 MarkdownChunker，避免 operator 内部再承载工具实现。
            3. 为后续 Markdown 读取、分块和 artifact 组装提供共享入口。

        Args:
            config (dict | None, optional): 分块配置，默认空字典。

        Returns:
            None: 构造函数不返回值。

        Examples:
            >>> MarkdownChunkArtifactBuilder({"target_len": 10}).chunker.config["target_len"]
            10
        """
        self.chunker = MarkdownChunker(config or {})

    def resolve_markdown(self, item: DataItem) -> str:
        """从数据项中解析可分块的 Markdown 文本

        业务逻辑：
            1. 优先读取 `item.intermediate["markdown"]`。
            2. 若中间态不存在，则逆序回退到最近的 `markdown` artifact。
            3. 若仍无可用文本，则返回空字符串。

        Args:
            item (DataItem): 当前正在处理的数据项。

        Returns:
            str: 可用于分块的 Markdown 文本。

        Examples:
            >>> MarkdownChunkArtifactBuilder().resolve_markdown(DataItem(id="x", source={"path": "x"}, payload={}))
            ''
        """
        markdown = item.intermediate.get("markdown")
        if isinstance(markdown, str):
            return markdown
        for artifact in reversed(item.artifacts):
            if artifact.type == "markdown" and artifact.text:
                return artifact.text
        return ""

    def build_chunk_artifacts(self, item: DataItem, markdown: str, operator_name: str) -> list[Artifact]:
        """根据 Markdown 文本构造分块 artifacts

        业务逻辑：
            1. 使用共享 chunker 执行 Markdown 分块。
            2. 为每个 chunk 分配稳定的序号、总数和 target_len 元数据。
            3. 返回待追加的 `markdown_chunk` artifacts，供 operator 决定写入时机。

        Args:
            item (DataItem): 当前数据项，用于生成 artifact id 和 source_trace。
            markdown (str): 待分块的 Markdown 文本。
            operator_name (str): 写入 source_trace 的 operator 名称。

        Returns:
            list[Artifact]: 构造好的 Markdown 分块产物列表。

        Examples:
            >>> item = DataItem(id="demo", source={"path": "demo.md"}, payload={})
            >>> artifacts = MarkdownChunkArtifactBuilder({"target_len": 8}).build_chunk_artifacts(item, "A. B.", "markdown_chunk")
            >>> artifacts[0].type
            'markdown_chunk'
        """
        chunks = self.chunker.chunk(markdown)
        target_len = int(self.chunker.config.get("target_len", 1500))
        total = len(chunks)
        artifacts: list[Artifact] = []
        for index, chunk_text in enumerate(chunks, start=1):
            artifacts.append(
                Artifact(
                    id=f"{item.id}_chunk_{index}",
                    type="markdown_chunk",
                    text=chunk_text,
                    data={"chunk_index": index, "chunk_count": total, "target_len": target_len},
                    source_trace=SourceTrace(file=item.source["path"], operator=operator_name),
                )
            )
        return artifacts
