"""Write a safe, public representation of a diagnostic record."""
import json
import math

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


# These are the fields exposed by the diagnostic format.  Keeping this list
# explicit prevents implementation details attached to an exception/record
# from accidentally becoming part of the log format.
_RECORD_FIELDS = ('correlation', 'message', 'code', 'error', 'children')
_ERROR_FIELDS = ('type', 'message', 'code', 'details')


def _scalar(value):
    """Return a JSON scalar, using ``None`` for unsupported values."""
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        # json.dumps accepts NaN and infinities by default, but those are not
        # portable JSON values and make a diagnostic harder to consume.
        return value if math.isfinite(value) else None
    return None


def _details(value, depth=0):
    """Make error details JSON-safe without allowing unbounded structures."""
    if value is None or type(value) in (str, int, float, bool):
        return _scalar(value)
    if depth >= X06_MAX_DEPTH:
        return None
    if type(value) is list:
        return [_details(item, depth + 1) for item in value[:X06_MAX_CHILDREN]]
    if type(value) is dict:
        return {
            key: _details(item, depth + 1)
            for key, item in value.items()
            if type(key) is str
        }
    return None


def _error(value):
    if type(value) is not dict:
        return None
    return {
        name: _details(value[name])
        for name in _ERROR_FIELDS
        if name in value
    }


def _record(value, depth=0):
    if type(value) is not dict:
        return {}

    record = {}
    for name in ('correlation', 'message', 'code'):
        if name in value:
            record[name] = _scalar(value[name])

    if 'error' in value:
        error = _error(value['error'])
        if error is not None:
            record['error'] = error

    if 'children' in value and type(value['children']) is list and depth < X06_MAX_DEPTH:
        record['children'] = [
            _record(child, depth + 1)
            for child in value['children'][:X06_MAX_CHILDREN]
            if type(child) is dict
        ]
    return record


def run(diagnostic_record, sink):
    """Serialize a diagnostic and report whether it reached *sink*."""
    try:
        sink.write(json.dumps(_record(diagnostic_record), allow_nan=False))
    except Exception:
        return 'log-error'
    return 'logged'
