"""Baseline support for the original version-one string records."""

import json


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError('duplicate field')
        result[name] = value
    return result


def _constant(value):
    raise ValueError('invalid number')


def run(decoder, encoded_record_bytes):
    try:
        if type(encoded_record_bytes) is not bytes:
            raise ValueError('bytes required')
        record = json.loads(encoded_record_bytes.decode('utf-8'),
                            object_pairs_hook=_pairs, parse_constant=_constant)
        if type(record) is not dict or set(record) != {'version', 'data'}:
            raise ValueError('invalid record')
        if type(record['version']) is not int or record['version'] != 1:
            raise ValueError('unsupported version')
        if type(record['data']) is not str:
            raise ValueError('unsupported data')
        return ('ok', record['data'])
    except (ValueError, RecursionError) as error:
        return ('invalid', str(error))
