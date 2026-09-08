"""Public diagnostic log serialization."""
import json

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


_DIAGNOSTIC_FIELDS = ("correlation", "message", "code", "children", "error")
_ERROR_FIELDS = ("type", "code", "message")
_SCALAR_TYPES = (str, int, float, bool)


def _public_scalar(value):
    if value is None or type(value) in _SCALAR_TYPES:
        return value
    return None


def _copy_scalar_field(source, target, field):
    if field in source:
        value = source[field]
        if value is None or type(value) in _SCALAR_TYPES:
            target[field] = value


def _public_error(error):
    if type(error) is not dict:
        return None

    public = {}
    for field in _ERROR_FIELDS:
        _copy_scalar_field(error, public, field)
    return public


def _public_record(diagnostic_record, depth=0):
    if type(diagnostic_record) is not dict:
        return {}

    record = {}
    for field in _DIAGNOSTIC_FIELDS:
        if field == "correlation":
            if field in diagnostic_record:
                record[field] = _public_scalar(diagnostic_record[field])
        elif field == "children":
            if field in diagnostic_record and depth < X06_MAX_DEPTH:
                children = diagnostic_record[field]
                if type(children) is list:
                    public_children = []
                    for child in children[:X06_MAX_CHILDREN]:
                        public_children.append(_public_record(child, depth + 1))
                    record[field] = public_children
        elif field == "error":
            if field in diagnostic_record:
                error = _public_error(diagnostic_record[field])
                if error is not None:
                    record[field] = error
        else:
            _copy_scalar_field(diagnostic_record, record, field)
    return record


def run(diagnostic_record, sink):
    record = _public_record(diagnostic_record)
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
