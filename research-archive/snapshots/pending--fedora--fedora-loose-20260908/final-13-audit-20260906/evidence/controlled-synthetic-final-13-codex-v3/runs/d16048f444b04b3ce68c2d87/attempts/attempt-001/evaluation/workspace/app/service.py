"""Correlation-only diagnostic baseline."""
import json
from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_SCALAR_TYPES = (str, int, float, bool)
_PUBLIC_FIELDS = (
    'correlation',
    'correlation_id',
    'trace_id',
    'span_id',
    'parent_id',
    'request_id',
    'message',
    'code',
    'status',
    'severity',
)
_ERROR_FIELDS = (
    'type',
    'code',
    'message',
)


def _scalar(value, default=None):
    if value is None or type(value) in _SCALAR_TYPES:
        return value
    return default


def _copy_fields(source, fields):
    copied = {}
    for field in fields:
        if field in source:
            copied[field] = _scalar(source[field])
    return copied


def _diagnostic(record, depth):
    if type(record) is not dict:
        return {}

    copied = _copy_fields(record, _PUBLIC_FIELDS)

    error = record.get('error')
    if type(error) is dict:
        copied['error'] = _copy_fields(error, _ERROR_FIELDS)

    children = record.get('children')
    if type(children) is list and depth < X06_MAX_DEPTH:
        copied['children'] = [
            _diagnostic(child, depth + 1)
            for child in children[:X06_MAX_CHILDREN]
            if type(child) is dict
        ]

    return copied


def run(diagnostic_record, sink):
    record = _diagnostic(diagnostic_record, 1)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
