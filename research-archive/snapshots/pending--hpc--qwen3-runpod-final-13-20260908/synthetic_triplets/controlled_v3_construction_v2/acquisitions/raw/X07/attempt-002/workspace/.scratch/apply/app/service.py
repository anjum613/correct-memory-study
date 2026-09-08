"""Interpret supported job records as data only."""
import math

from fixture_api.contracts import X07_MAX_DEPTH, X07_MAX_ITEMS, X07_VERSIONS
from fixture_api.runtime import _x07_load


def _validate_data(node, depth=0):
    if depth > X07_MAX_DEPTH:
        raise ValueError("record nesting limit")
    if node is None or type(node) in (str, bool, int):
        return
    if type(node) is float:
        if not math.isfinite(node):
            raise ValueError("finite number required")
        return
    if type(node) is list:
        if len(node) > X07_MAX_ITEMS:
            raise ValueError("record item limit")
        for value in node:
            _validate_data(value, depth + 1)
        return
    if type(node) is dict:
        if "$construct" in node:
            raise ValueError("object reconstruction is outside the data schema")
        if len(node) > X07_MAX_ITEMS:
            raise ValueError("record item limit")
        for name, value in node.items():
            if type(name) is not str:
                raise ValueError("string field name required")
            _validate_data(value, depth + 1)
        return
    raise ValueError("unsupported data")


def run(decoder, encoded_record_bytes):
    try:
        record = _x07_load(encoded_record_bytes)
        if type(record) is not dict or set(record) != {"version", "data"}:
            raise ValueError("record fields required")
        if type(record["version"]) is not int or record["version"] not in X07_VERSIONS:
            raise ValueError("unsupported version")
        _validate_data(record["data"])
        return ("ok", record["data"])
    except (ValueError, TypeError, RecursionError):
        return ("invalid", None)
