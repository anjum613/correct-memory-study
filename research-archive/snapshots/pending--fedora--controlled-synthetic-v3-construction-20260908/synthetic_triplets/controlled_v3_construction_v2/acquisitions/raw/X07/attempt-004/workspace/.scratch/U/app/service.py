"""Decode supported records from the trusted internal producer."""
import math

from fixture_api.contracts import X07_VERSIONS, X07_MAX_DEPTH, X07_MAX_ITEMS
from fixture_api.runtime import _x07_load


def _validate(value, depth=0):
    if depth > X07_MAX_DEPTH:
        raise ValueError('depth')
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return
    if kind is float:
        if not math.isfinite(value):
            raise ValueError('number')
        return
    if kind is list:
        if len(value) > X07_MAX_ITEMS:
            raise ValueError('items')
        for item in value:
            _validate(item, depth + 1)
        return
    if kind is dict:
        if len(value) > X07_MAX_ITEMS:
            raise ValueError('items')
        for name, item in value.items():
            if type(name) is not str:
                raise ValueError('field name')
            _validate(item, depth + 1)
        return
    raise ValueError('data')


def run(decoder, encoded_record_bytes):
    try:
        record = _x07_load(encoded_record_bytes)
        if type(record) is not dict or set(record) != {'version', 'data'}:
            raise ValueError('record fields')
        if type(record['version']) is not int or record['version'] not in X07_VERSIONS:
            raise ValueError('version')
        _validate(record['data'])
        return ('ok', decoder.reconstruct(record['data']))
    except (ValueError, TypeError, RecursionError, OverflowError):
        return ('invalid', None)
