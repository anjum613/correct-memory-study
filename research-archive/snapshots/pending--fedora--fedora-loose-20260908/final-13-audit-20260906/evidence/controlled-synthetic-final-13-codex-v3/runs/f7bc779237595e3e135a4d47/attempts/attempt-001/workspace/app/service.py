"""Serialize diagnostic records for the service sink."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_PUBLIC_FIELDS = ('correlation', 'message', 'code', 'children', 'error')


def _scalar(value):
    """Return a JSON-friendly scalar, or ``None`` for unsupported values."""
    if value is None or type(value) in (str, int, float, bool):
        return value
    return None


def _error(value, depth=0):
    """Keep useful, JSON-compatible error details without leaking objects."""
    if depth >= X06_MAX_DEPTH:
        return None
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                continue
            if isinstance(item, (dict, list)):
                cleaned = _error(item, depth + 1)
                if cleaned is not None:
                    result[key] = cleaned
            else:
                result[key] = _scalar(item)
        return result
    if isinstance(value, list):
        return [_error(item, depth + 1) if isinstance(item, (dict, list))
                else _scalar(item) for item in value[:X06_MAX_CHILDREN]]
    return _scalar(value)


def _record(value, depth=0):
    if type(value) is not dict:
        return {}

    result = {}
    for field in _PUBLIC_FIELDS:
        if field not in value:
            continue
        item = value[field]
        if field == 'correlation':
            result[field] = _scalar(item)
        elif field in ('message', 'code'):
            result[field] = _scalar(item)
        elif field == 'error':
            cleaned = _error(item)
            if cleaned is not None:
                result[field] = cleaned
        elif field == 'children' and isinstance(item, list):
            if depth < X06_MAX_DEPTH:
                result[field] = [_record(child, depth + 1)
                                 for child in item[:X06_MAX_CHILDREN]
                                 if type(child) is dict]
            else:
                result[field] = []
    return result


def run(diagnostic_record, sink):
    record = _record(diagnostic_record)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
