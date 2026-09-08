"""Project public diagnostic fields before serializing to the log."""
import json


_MAX_DEPTH = 4
_MAX_CHILDREN = 8
_MISSING = object()


def _field(record, name):
    """Read a named field without converting the enclosing object to text."""
    try:
        if isinstance(record, dict):
            return dict.get(record, name, _MISSING)
        return getattr(record, name, _MISSING)
    except Exception:
        return _MISSING


def _scalar_fields(record, names):
    result = {}
    for name in names:
        value = _field(record, name)
        if value is None or type(value) in (str, bool, int, float):
            result[name] = value
    return result


def _error(error):
    if error is None:
        return None
    result = _scalar_fields(error, ('type', 'code'))
    if isinstance(error, BaseException) and 'type' not in result:
        result['type'] = type(error).__name__
    return result


def _project(record, depth, ancestors):
    result = _scalar_fields(record, ('correlation', 'message', 'code'))
    error = _field(record, 'error')
    if error is not _MISSING:
        result['error'] = _error(error)
    children = _field(record, 'children')
    if type(children) in (list, tuple):
        result['children'] = []
        if depth < _MAX_DEPTH:
            for child in children[:_MAX_CHILDREN]:
                if id(child) not in ancestors:
                    result['children'].append(
                        _project(child, depth + 1, ancestors + (id(child),))
                    )
    return result


def run(diagnostic_record, sink):
    try:
        public_record = _project(diagnostic_record, 0, (id(diagnostic_record),))
        line = json.dumps(public_record)
        sink.write(line)
    except Exception:
        # Neither input nor exception representations belong in failure output.
        return 'log-error'
    return 'logged'
