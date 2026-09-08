import pytest

from record_parser import parse_record


def test_splits_only_the_first_equals_sign():
    assert parse_record("expression=a=b=c") == {"expression": "a=b=c"}


def test_multiple_fields_and_trailing_separator():
    assert parse_record("a=1;b=two;") == {"a": "1", "b": "two"}


def test_empty_value_is_allowed():
    assert parse_record("optional=") == {"optional": ""}


def test_empty_record_is_allowed():
    assert parse_record(" ; ") == {}


def test_missing_equals_is_rejected():
    with pytest.raises(ValueError):
        parse_record("valid=1;invalid")


def test_empty_key_is_rejected():
    with pytest.raises(ValueError):
        parse_record(" =value")


def test_duplicate_key_is_rejected():
    with pytest.raises(ValueError):
        parse_record("name=first;name=second")
