"""Decode the original internal version-one string records."""
from fixture_api.runtime import _x07_load


def run(decoder, encoded_record_bytes):
    try:
        record = _x07_load(encoded_record_bytes)
        if type(record) is not dict or set(record) != {'version', 'data'}:
            raise ValueError('record fields')
        if type(record['version']) is not int or record['version'] != 1:
            raise ValueError('unsupported version')
        data = decoder.reconstruct(record['data'])
        if type(data) is not str:
            raise ValueError('string required')
        return ('ok', data)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return ('invalid', None)
