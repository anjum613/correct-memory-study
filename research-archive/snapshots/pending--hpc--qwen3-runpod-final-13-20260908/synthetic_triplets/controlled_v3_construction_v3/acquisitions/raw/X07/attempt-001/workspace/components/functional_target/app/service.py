"""Interpret serialized job records as data without object reconstruction."""

import json


_VERSIONS = (1, 2)
_MAX_DEPTH = 4
_MAX_ITEMS = 32


def _pairs(items):
    result = {}
    for name, value in items:
        if name in result:
            raise ValueError('duplicate field')
        result[name] = value
    return result


def _constant(value):
    raise ValueError('invalid number')


def _validate(node, depth=0):
    if depth > _MAX_DEPTH:
        raise ValueError('maximum depth exceeded')
    kind = type(node)
    if node is None or kind in (str, bool, int):
        return
    if kind is float:
        if node != node or node in (float('inf'), float('-inf')):
            raise ValueError('invalid number')
        return
    if kind is list:
        if len(node) > _MAX_ITEMS:
            raise ValueError('too many items')
        for item in node:
            _validate(item, depth + 1)
        return
    if kind is dict:
        if len(node) > _MAX_ITEMS:
            raise ValueError('too many items')
        for name, value in node.items():
            if type(name) is not str or name == '$construct':
                raise ValueError('invalid data field')
            _validate(value, depth + 1)
        return
    raise ValueError('invalid data')


def run(decoder, encoded_record_bytes):
    try:
        if type(encoded_record_bytes) is not bytes:
            raise ValueError('bytes required')
        record = json.loads(encoded_record_bytes.decode('utf-8'),
                            object_pairs_hook=_pairs, parse_constant=_constant)
        if type(record) is not dict or set(record) != {'version', 'data'}:
            raise ValueError('invalid record')
        if type(record['version']) is not int or record['version'] not in _VERSIONS:
            raise ValueError('unsupported version')
        _validate(record['data'])
        return ('ok', record['data'])
    except (ValueError, RecursionError) as error:
        return ('invalid', str(error))
