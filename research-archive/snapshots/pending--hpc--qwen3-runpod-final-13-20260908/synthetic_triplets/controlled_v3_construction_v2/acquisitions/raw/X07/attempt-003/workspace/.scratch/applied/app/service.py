"""Interpret supported records as data without invoking object reconstruction."""
import math

from fixture_api.contracts import X07_MAX_DEPTH, X07_MAX_ITEMS, X07_VERSIONS
from fixture_api.runtime import _x07_load


def _validate_data(value, depth=0):
    if depth > X07_MAX_DEPTH:
        raise ValueError('data nesting')
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('nonfinite number')
        return
    if type(value) is list:
        if len(value) > X07_MAX_ITEMS:
            raise ValueError('too many items')
        for item in value:
            _validate_data(item, depth + 1)
        return
    if type(value) is dict:
        if len(value) > X07_MAX_ITEMS:
            raise ValueError('too many fields')
        for name, item in value.items():
            if type(name) is not str:
                raise ValueError('field name')
            if name == '$construct':
                raise ValueError('object reconstruction is outside the data schema')
            _validate_data(item, depth + 1)
        return
    raise ValueError('unsupported data')


def run(decoder, encoded_record_bytes):
    try:
        record = _x07_load(encoded_record_bytes)
        if type(record) is not dict or set(record) != {'version', 'data'}:
            raise ValueError('record fields')
        if type(record['version']) is not int or record['version'] not in X07_VERSIONS:
            raise ValueError('unsupported version')
        data = record['data']
        _validate_data(data)
        return ('ok', data)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return ('invalid', None)
