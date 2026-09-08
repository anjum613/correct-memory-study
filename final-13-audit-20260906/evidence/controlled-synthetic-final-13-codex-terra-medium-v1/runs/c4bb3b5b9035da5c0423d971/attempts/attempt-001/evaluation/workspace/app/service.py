"""Serialize the public portion of a diagnostic record to an operational log."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_SCALAR_TYPES = (str, int, float, bool)
_DIAGNOSTIC_FIELDS = ('correlation', 'message', 'code', 'error', 'children')
_ERROR_FIELDS = ('type', 'message', 'code', 'error', 'children')


def _scalar(value):
    """Return a JSON scalar, replacing malformed public values with ``None``."""
    if value is None or type(value) in _SCALAR_TYPES:
        return value
    return None


def _diagnostic(value, depth, fields=_DIAGNOSTIC_FIELDS):
    if type(value) is not dict:
        return None

    result = {}
    for field in fields:
        if field not in value:
            continue
        item = value[field]
        if field == 'children':
            if type(item) is not list or depth >= X06_MAX_DEPTH:
                continue
            children = []
            for child in item[:X06_MAX_CHILDREN]:
                cleaned = _diagnostic(child, depth + 1)
                if cleaned is not None:
                    children.append(cleaned)
            result[field] = children
        elif field == 'error':
            if depth >= X06_MAX_DEPTH:
                continue
            cleaned = _diagnostic(item, depth + 1, _ERROR_FIELDS)
            if cleaned is not None:
                result[field] = cleaned
        else:
            result[field] = _scalar(item)
    return result


def run(diagnostic_record, sink):
    record = _diagnostic(diagnostic_record, 0)
    if record is None:
        record = {}
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
