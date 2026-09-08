import pytest

from pagination import page_slice


def test_page_one_and_later_pages():
    values = list(range(7))
    assert page_slice(values, 1, 3) == [0, 1, 2]
    assert page_slice(values, 3, 3) == [6]


def test_page_beyond_end_is_empty():
    assert page_slice([1, 2], 4, 2) == []


@pytest.mark.parametrize("name", ["page", "page_size"])
def test_boolean_is_not_an_integer_argument(name):
    arguments = {"page": 1, "page_size": 1}
    arguments[name] = True
    with pytest.raises(TypeError):
        page_slice([1], **arguments)


def test_non_integer_is_rejected():
    with pytest.raises(TypeError):
        page_slice([1], 1.0, 1)


@pytest.mark.parametrize("page,page_size", [(0, 1), (-1, 1), (1, 0), (1, -1)])
def test_non_positive_values_are_rejected(page, page_size):
    with pytest.raises(ValueError):
        page_slice([1], page, page_size)
