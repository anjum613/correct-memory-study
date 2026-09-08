from normalizer import normalize_display_label


def test_normalizes_edges_and_case() -> None:
    assert normalize_display_label("  Example Label  ") == "example label"
