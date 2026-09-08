"""Write the public, bounded form of a diagnostic record to an operational log."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


# Copying an arbitrary mapping here would make a caller adding a private
# attribute an accidental logging API change.
_DIAGNOSTIC_FIELDS = ('correlation', 'message', 'code', 'children', 'error')
_ERROR_FIELDS = ('type', 'message', 'code', 'correlation', 'children', 'error')
_SCALAR_TYPES = (str, int, float, bool)


def _scalar(value):
    """Return a JSON scalar, retaining the baseline's null fallback."""
    if value is None or type(value) in _SCALAR_TYPES:
        return value
    return None


def _record(value, depth=0, error=False):
    """Extract public diagnostics without following unbounded input graphs."""
    if type(value) is not dict:
        return None

    fields = _ERROR_FIELDS if error else _DIAGNOSTIC_FIELDS
    output = {}
    for name in fields:
        if name not in value:
            continue
        item = value[name]
        if name == 'children':
            if type(item) is not list or depth >= X06_MAX_DEPTH:
                output[name] = [] if type(item) is list else None
            else:
                output[name] = [
                    _record(child, depth + 1)
                    for child in item[:X06_MAX_CHILDREN]
                    if type(child) is dict
                ]
        elif name == 'error':
            output[name] = (
                _record(item, depth + 1, error=True)
                if depth < X06_MAX_DEPTH else None
            )
        else:
            output[name] = _scalar(item)
    return output


def run(diagnostic_record, sink):
    record = _record(diagnostic_record)
    if record is None:
        record = {}
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
