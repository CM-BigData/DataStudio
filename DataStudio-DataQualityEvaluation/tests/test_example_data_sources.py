from pathlib import Path


DATA_ROOTS = [
    Path("example_data"),
    Path("real_data"),
]

TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md"}
REQUIRED_DATASET_NAMES = {
    "Project Gutenberg",
    "Mini LibriSpeech",
    "Oxford-IIIT Pet",
}
OLD_NON_DATASET_SOURCE_TERMS = {
    "MDN",
    "PyTorch Hub",
    "python-docx",
    "scikit-image",
    "skimage",
    "National Fossil",
    "Manual realistic",
    "Manual documentation",
    "Manual forum",
    "CLUE TNEWS",
    "Zhihu",
    "v2ex",
}


def _read_data_source_text() -> str:
    """Collect text-bearing sample metadata for source-origin assertions.

    Business logic:
        1. Read source and annotation text from normal sample data directories.
        2. Skip binary sample files.
        3. Return one combined string for concise source-term assertions.

    Args:
        None.

    Returns:
        str: Combined UTF-8 text from source metadata and text samples.

    Examples:
        >>> isinstance(_read_data_source_text(), str)
        True
    """
    parts: list[str] = []
    for root in DATA_ROOTS:
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
                parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def test_sample_data_sources_are_open_dataset_based() -> None:
    """Verify sample data source metadata stays on open-dataset sources.

    Business logic:
        1. Read sample source metadata and text fixtures.
        2. Confirm the three intended open dataset sources are documented.
        3. Confirm older public-example or manual-source terms do not return.

    Args:
        None.

    Returns:
        None: Pytest raises on assertion failure.

    Examples:
        >>> callable(test_sample_data_sources_are_open_dataset_based)
        True
    """
    source_text = _read_data_source_text()

    for dataset_name in REQUIRED_DATASET_NAMES:
        assert dataset_name in source_text
    for old_term in OLD_NON_DATASET_SOURCE_TERMS:
        assert old_term not in source_text
