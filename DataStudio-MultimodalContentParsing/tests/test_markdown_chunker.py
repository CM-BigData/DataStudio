from parse_engine.models import Artifact, DataItem, SourceTrace
from parse_engine.operators.common import MarkdownChunkOperator
from parse_engine.runtime.registry import registry
from parse_engine.utilities.markdown.chunk import MarkdownChunkArtifactBuilder
from parse_engine.utilities.markdown.rebuild import MarkdownArtifactRebuilder, normalize_heading_level, table_to_markdown


def test_markdown_chunker_splits_chinese_sentences_and_newlines() -> None:
    """Verify that the Markdown chunker splits text by Chinese punctuation and newlines.

    Business logic:
        1. Build Markdown text containing Chinese periods, question marks, exclamation marks, and newlines.
        2. Use a small target_len to trigger multiple chunk merge boundaries.
        3. Assert that output chunks preserve the original sentences and produce multiple fragments.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "First sentence." in "First sentence."
        True"""
    from parse_engine.utilities.markdown.chunker import MarkdownChunker

    chunks = MarkdownChunker({"target_len": 12}).chunk("First sentence. Second sentence?\nThird sentence!")

    assert len(chunks) >= 2
    assert chunks[0].startswith("First sentence.")
    assert any("Third sentence!" in chunk for chunk in chunks)


def test_markdown_chunker_splits_long_tables_with_header() -> None:
    """Verify that the Markdown chunker preserves the header when splitting long tables.

    Business logic:
        1. Construct a Markdown table longer than target_len.
        2. Call MarkdownChunker to split the table.
        3. Assert that multiple chunks each contain the header and separator row.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "| Field | Value |".startswith("|")
        True"""
    from parse_engine.utilities.markdown.chunker import MarkdownChunker

    rows = ["| Field | Value |", "| --- | --- |"]
    rows.extend(f"| name_{index} | {'content ' * 10} |" for index in range(8))
    chunks = MarkdownChunker({"target_len": 90}).chunk("\n".join(rows))

    assert len(chunks) > 1
    assert all(chunk.startswith("| Field | Value |\n| --- | --- |") for chunk in chunks)


def test_markdown_chunk_operator_creates_chunk_artifacts_from_intermediate() -> None:
    """Verify that the markdown_chunk operator generates chunk artifacts from intermediate data.

    Business logic:
        1. Construct a DataItem containing intermediate markdown.
        2. Run MarkdownChunkOperator.
        3. Assert that markdown_chunk artifacts and chunk metrics are generated.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "markdown_chunk".endswith("chunk")
        True"""
    item = DataItem(id="demo", modality="word", source={"path": "demo.docx"}, payload={"path": "demo.docx"})
    item.intermediate["markdown"] = "First sentence. Second sentence."

    result = MarkdownChunkOperator({"target_len": 8}).process(item)

    chunk_artifacts = [artifact for artifact in result.artifacts if artifact.type == "markdown_chunk"]
    assert len(chunk_artifacts) == result.metrics["chunk_count"]
    assert chunk_artifacts[0].data["chunk_index"] == 1
    assert chunk_artifacts[0].data["target_len"] == 8
    assert chunk_artifacts[0].source_trace.operator == "markdown_chunk"


def test_markdown_chunk_operator_falls_back_to_markdown_artifact() -> None:
    """Verify that the markdown_chunk operator can fall back to reading from a markdown artifact.

    Business logic:
        1. Construct a DataItem with no intermediate markdown but with a markdown artifact.
        2. Run MarkdownChunkOperator.
        3. Assert that chunk artifacts are generated and no empty-Markdown issue is recorded.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "markdown" in {"markdown": True}
        True"""
    item = DataItem(id="demo", modality="word", source={"path": "demo.docx"}, payload={"path": "demo.docx"})
    item.artifacts.append(
        Artifact(
            id="demo_markdown",
            type="markdown",
            text="Content from artifact.",
            source_trace=SourceTrace(file="demo.docx", operator="markdown_rebuild"),
        )
    )

    result = MarkdownChunkOperator({"target_len": 1500}).process(item)

    assert any(artifact.type == "markdown_chunk" for artifact in result.artifacts)
    assert not any(issue["type"] == "empty_markdown_chunks" for issue in result.issues)


def test_markdown_chunk_utility_resolves_latest_markdown_artifact() -> None:
    """Verify that the chunk utility reads the latest markdown artifact when intermediate is missing.

    Business logic:
        1. Construct a DataItem without intermediate markdown.
        2. Append multiple markdown artifacts to simulate upstream rebuild history.
        3. Assert that the utility returns the newest markdown artifact text.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "latest".upper()
        'LATEST'
    """
    item = DataItem(id="demo", modality="word", source={"path": "demo.docx"}, payload={"path": "demo.docx"})
    item.artifacts.append(
        Artifact(
            id="demo_markdown_1",
            type="markdown",
            text="older",
            source_trace=SourceTrace(file="demo.docx", operator="markdown_rebuild"),
        )
    )
    item.artifacts.append(
        Artifact(
            id="demo_markdown_2",
            type="markdown",
            text="latest",
            source_trace=SourceTrace(file="demo.docx", operator="markdown_rebuild"),
        )
    )

    markdown = MarkdownChunkArtifactBuilder().resolve_markdown(item)

    assert markdown == "latest"


def test_markdown_rebuild_utility_rebuilds_heading_and_table_blocks() -> None:
    """Verify that the rebuild utility assembles headings, tables, and text into Markdown.

    Business logic:
        1. Build heading, table, and paragraph artifacts in source order.
        2. Run MarkdownArtifactRebuilder to reconstruct Markdown text.
        3. Assert that heading level normalization and table rendering both appear in the output.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> normalize_heading_level(9)
        6
    """
    item = DataItem(id="demo", modality="word", source={"path": "demo.docx"}, payload={"path": "demo.docx"})
    item.artifacts.append(
        Artifact(
            id="h1",
            type="heading",
            text="Title",
            data={"heading_level": 9},
            source_trace=SourceTrace(file="demo.docx", operator="word_parse"),
        )
    )
    item.artifacts.append(
        Artifact(
            id="t1",
            type="table",
            data={"rows": [["field", "value"], ["name", "demo"]]},
            source_trace=SourceTrace(file="demo.docx", operator="word_parse"),
        )
    )
    item.artifacts.append(
        Artifact(
            id="p1",
            type="paragraph",
            text="Summary",
            source_trace=SourceTrace(file="demo.docx", operator="word_parse"),
        )
    )

    markdown = MarkdownArtifactRebuilder().rebuild_markdown(item)

    assert markdown.startswith("###### Title")
    assert "| field | value |" in markdown
    assert "Summary" in markdown


def test_markdown_rebuild_utility_helpers_keep_output_stable() -> None:
    """Verify that rebuild helper utilities keep legacy-compatible normalization behavior.

    Business logic:
        1. Validate heading level fallback and clamp behavior.
        2. Validate Markdown table rendering for a small two-row table.
        3. Keep direct coverage on utilities now that helper logic no longer lives in operator files.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> table_to_markdown([["a"], ["b"]])[0]
        '| a |'
    """
    assert normalize_heading_level(None) == 2
    assert normalize_heading_level(0) == 1
    assert normalize_heading_level(9) == 6
    assert table_to_markdown([["field", "value"], ["name", "demo"]]) == [
        "| field | value |",
        "| --- | --- |",
        "| name | demo |",
    ]


def test_markdown_chunk_stage_is_not_registered_as_public_operator() -> None:
    """Verify that the markdown_chunk internal stage is not exposed through the registry.

    Business logic:
        1. Keep direct import coverage for the internal MarkdownChunkOperator stage.
        2. Try to create the legacy markdown_chunk registry name.
        3. Assert that runtime registry no longer exposes the internal stage.

    Args:
        None.

    Returns:
        None: pytest reports an error if an assertion fails.

    Examples:
        >>> "markdown_chunk".islower()
        True"""
    try:
        registry.create("markdown_chunk", {})
    except KeyError:
        pass
    else:
        raise AssertionError("markdown_chunk should not be registered as a public operator")
