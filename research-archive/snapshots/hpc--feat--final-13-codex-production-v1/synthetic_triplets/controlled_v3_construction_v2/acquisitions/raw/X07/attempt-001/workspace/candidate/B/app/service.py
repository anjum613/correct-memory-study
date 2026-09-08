"""Decode internal version-one string records."""
from fixture_api.runtime import _x07_load


def run(decoder, encoded_record_bytes):
    try:
        record = _x07_load(encoded_record_bytes)
        if type(record) is not dict or set(record) != {"version", "data"}:
            raise ValueError("invalid record")
        if type(record["version"]) is not int or record["version"] != 1:
            raise ValueError("unsupported version")
        if type(record["data"]) is not str:
            raise ValueError("string required")
        return ("ok", decoder.reconstruct(record["data"]))
    except (ValueError, TypeError, RecursionError):
        return ("invalid", None)
