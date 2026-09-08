import pytest

from dependency_order import installation_order


def test_dependency_precedes_dependant():
    assert installation_order({"app": ("database",), "database": ()}) == [
        "database",
        "app",
    ]


def test_cycle_is_rejected():
    with pytest.raises(ValueError):
        installation_order({"a": ("b",), "b": ("a",)})
