"""Decode supported internal records using the producer's reconstruction API."""
import math

from fixture_api import contracts as k
from fixture_api.runtime import _x07_load


def _validate_data(node, depth=0):
    if depth > k.X07_MAX_DEPTH:
        raise ValueError("record too deep")
    kind = type(node)
    if node is None or kind in (str, bool, int):
        return
    if kind is float and math.isfinite(node):
        return
    if kind is list:
        if len(node) > k.X07_MAX_ITEMS:
            raise ValueError("too many items")
        for item in node:
            _validate_data(item, depth + 1)
        return
    if kind is dict:
        if len(node) > k.X07_MAX_ITEMS:
            raise ValueError("too many fields")
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
            raise ValueError("invalid record")
        if type(record["version"]) is not int or record["version"] not in k.X07_VERSIONS:
            raise ValueError("unsupported version")
        _validate_data(record["data"])
        return ("ok", decoder.reconstruct(record["data"]))
    except (ValueError, TypeError, RecursionError):
        return ("invalid", None)
