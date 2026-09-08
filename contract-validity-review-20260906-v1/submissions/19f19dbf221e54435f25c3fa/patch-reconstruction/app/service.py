"""Public diagnostic log shaping."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_PUBLIC_FIELDS = ('correlation', 'message', 'code')
_ERROR_FIELDS = ('type', 'message', 'code')


def _public_value(value):
    if value is None or type(value) in (str, int, float, bool):
        return value
    return None


def _shape_error(error):
    if type(error) is not dict:
        return None
    shaped = {}
    for field in _ERROR_FIELDS:
        if field in error:
            shaped[field] = _public_value(error[field])
    return shaped


def _shape_record(diagnostic_record, depth=0):
    if type(diagnostic_record) is not dict:
        return {}

    record = {}
    for field in _PUBLIC_FIELDS:
        if field in diagnostic_record:
            record[field] = _public_value(diagnostic_record[field])

    if 'error' in diagnostic_record:
        record['error'] = _shape_error(diagnostic_record['error'])

    if depth < X06_MAX_DEPTH and type(diagnostic_record.get('children')) is list:
        record['children'] = [
            _shape_record(child, depth + 1)
            for child in diagnostic_record['children'][:X06_MAX_CHILDREN]
        ]
    return record


def run(diagnostic_record, sink):
    record = _shape_record(diagnostic_record)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
