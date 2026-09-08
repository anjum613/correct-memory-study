"""Write a bounded, JSON-safe public diagnostic record."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_SCALAR_TYPES = (str, int, float, bool)
_DETAIL_FIELDS = ('type', 'message', 'code')


def _scalar(value):
    """Return whether *value* has the same scalar semantics as the baseline."""
    return value is None or type(value) in _SCALAR_TYPES


def _error_details(value):
    """Keep the public, useful parts of an error without accepting arbitrary data."""
    if type(value) is not dict:
        return None

    details = {}
    for field in _DETAIL_FIELDS:
        if field in value and _scalar(value[field]):
            details[field] = value[field]
    return details


def _record(value, depth=0):
    """Project one diagnostic node onto the documented output shape."""
    if type(value) is not dict:
        return {}

    result = {}

    # This deliberately matches the old correlation-only behavior: an invalid
    # supplied correlation is represented as null, rather than omitted.
    if 'correlation' in value:
        result['correlation'] = value['correlation'] if _scalar(value['correlation']) else None

    for field in ('message', 'code'):
        if field in value and _scalar(value[field]):
            result[field] = value[field]

    if 'error' in value:
        error = _error_details(value['error'])
        if error is not None:
            result['error'] = error

    if depth < X06_MAX_DEPTH and type(value.get('children')) is list:
        children = []
        for child in value['children'][:X06_MAX_CHILDREN]:
            if type(child) is dict:
                children.append(_record(child, depth + 1))
        result['children'] = children

    return result


def run(diagnostic_record, sink):
    try:
        sink.write(json.dumps(_record(diagnostic_record)))
    except Exception:
        return 'log-error'
    return 'logged'
