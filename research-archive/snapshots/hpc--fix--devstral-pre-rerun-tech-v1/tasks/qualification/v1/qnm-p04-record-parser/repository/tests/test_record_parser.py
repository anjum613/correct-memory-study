import pytest

from record_parser import parse_record


def test_value_may_contain_equals_signs():
    assert parse_record("name=demo;token=a=b=c") == {
        "name": "demo",
        "token": "a=b=c",
    }


def test_surrounding_whitespace_is_ignored():
    assert parse_record(" name = Ada ; role = engineer ") == {
        "name": "Ada",
        "role": "engineer",
    }


def test_missing_separator_is_rejected():
    with pytest.raises(ValueError):
        parse_record("name=Ada;broken")
