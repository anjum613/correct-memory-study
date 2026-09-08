"""Safely serialize the public portion of a diagnostic record."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


# These are deliberately an allow-list. Diagnostic records often accompany
# requests or exceptions, which can contain credentials and other operational
# data that do not belong in this log.
_DIAGNOSTIC_FIELDS = ('correlation', 'message', 'code')
_ERROR_FIELDS = ('type', 'message', 'code')
_SCALAR_TYPES = (str, int, float, bool)


def _scalar(value):
    """Return a JSON scalar, or None for an unsupported value."""
    if value is None or type(value) in _SCALAR_TYPES:
        return value
    return None


def _error(value):
    if type(value) is not dict:
        return None
    result = {}
    for field in _ERROR_FIELDS:
        if field in value:
            result[field] = _scalar(value[field])
    return result


def _diagnostic(value, depth=0):
    if type(value) is not dict:
        return {}

    result = {}
    for field in _DIAGNOSTIC_FIELDS:
        if field in value:
            result[field] = _scalar(value[field])

    if 'error' in value:
        result['error'] = _error(value['error'])

    # A child at depth four is still recorded, but is not expanded further.
    if depth < X06_MAX_DEPTH and type(value.get('children')) is list:
        result['children'] = [
            _diagnostic(child, depth + 1)
            for child in value['children'][:X06_MAX_CHILDREN]
        ]

    return result


def run(diagnostic_record, sink):
    record = _diagnostic(diagnostic_record)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
