from parse_engine.runtime.input_adapter import DataItemNormalizer


def test_parse_path_field_uses_pure_path_for_format_and_id() -> None:
    """Verify path-like input fields are parsed without filesystem resolution."""
    item = DataItemNormalizer().normalize({"path": r"C:\private\slides\deck.pdf"})

    assert item.id == "deck"
    assert item.source["format"] == "pdf"
    assert item.payload["path"] == r"C:\private\slides\deck.pdf"
