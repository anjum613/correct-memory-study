"""Public diagnostic serializer."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_PUBLIC_FIELDS = ('correlation', 'message', 'code')
_ERROR_FIELDS = ('type', 'message', 'code')
_SCALAR_TYPES = (str, int, float, bool)


def _public_scalar(value, *, null_for_invalid=False):
    if value is None or type(value) in _SCALAR_TYPES:
        return value
    if null_for_invalid:
        return None
    return _MISSING


def _sanitize_error(value):
    if not isinstance(value, dict):
        return _MISSING

    error = {}
    for field in _ERROR_FIELDS:
        if field in value:
            sanitized = _public_scalar(value[field])
            if sanitized is not _MISSING:
                error[field] = sanitized
    return error if error else _MISSING


def _sanitize_record(value, depth):
    if not isinstance(value, dict):
        return {}

    record = {}
    for field in _PUBLIC_FIELDS:
        if field in value:
            sanitized = _public_scalar(
                value[field],
                null_for_invalid=(field == 'correlation'),
            )
            if sanitized is not _MISSING:
                record[field] = sanitized

    if 'error' in value:
        error = _sanitize_error(value['error'])
        if error is not _MISSING:
            record['error'] = error

    if depth < X06_MAX_DEPTH and isinstance(value.get('children'), list):
        children = []
        for child in value['children'][:X06_MAX_CHILDREN]:
            if isinstance(child, dict):
                children.append(_sanitize_record(child, depth + 1))
        if children:
            record['children'] = children

    return record


_MISSING = object()


def run(diagnostic_record, sink):
    record = _sanitize_record(diagnostic_record, 1)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
