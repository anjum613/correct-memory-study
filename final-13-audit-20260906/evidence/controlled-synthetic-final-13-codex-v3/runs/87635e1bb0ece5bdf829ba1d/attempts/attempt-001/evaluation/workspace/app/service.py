"""Diagnostic record service."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_FIELDS = ('correlation', 'message', 'code', 'children', 'error')
_ERROR_FIELDS = ('type', 'code', 'message', 'details', 'stack', 'cause')


def _json_value(value, depth, seen):
    """Return a JSON-safe copy, keeping nested diagnostics bounded."""
    if value is None or type(value) in (str, int, float, bool):
        return value

    if type(value) is dict:
        marker = id(value)
        if marker in seen:
            return None
        seen.add(marker)
        result = {}
        for key, item in value.items():
            if type(key) is str:
                result[key] = _json_value(item, depth, seen)
        seen.remove(marker)
        return result

    if type(value) is list:
        marker = id(value)
        if marker in seen:
            return None
        seen.add(marker)
        result = [_json_value(item, depth, seen) for item in value]
        seen.remove(marker)
        return result

    return None


def _diagnostic(record, depth=0, seen=None):
    if type(record) is not dict:
        return {}
    if seen is None:
        seen = set()

    result = {}
    for field in _FIELDS:
        if field not in record:
            continue
        value = record[field]

        if field == 'correlation':
            # Keep the baseline's handling of an unusable correlation id.
            result[field] = value if value is None or type(value) in (str, int, float, bool) else None
        elif field == 'children':
            if type(value) is list and depth < X06_MAX_DEPTH:
                result[field] = [
                    _diagnostic(child, depth + 1, seen)
                    for child in value[:X06_MAX_CHILDREN]
                    if type(child) is dict
                ]
        elif field == 'error':
            if type(value) is dict:
                result[field] = {
                    key: _json_value(value[key], depth + 1, seen)
                    for key in _ERROR_FIELDS
                    if key in value
                }
        else:
            cleaned = _json_value(value, depth, seen)
            if cleaned is not None or value is None:
                result[field] = cleaned
    return result


def run(diagnostic_record, sink):
    record = _diagnostic(diagnostic_record)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
