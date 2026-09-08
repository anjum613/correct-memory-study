import pytest

from pagination import page_slice


def test_first_page_starts_with_first_item():
    assert page_slice(["a", "b", "c", "d"], 1, 2) == ["a", "b"]


def test_second_page_uses_next_window():
    assert page_slice(["a", "b", "c", "d"], 2, 2) == ["c", "d"]


def test_zero_page_is_rejected():
    with pytest.raises(ValueError):
        page_slice([1, 2], 0, 1)
