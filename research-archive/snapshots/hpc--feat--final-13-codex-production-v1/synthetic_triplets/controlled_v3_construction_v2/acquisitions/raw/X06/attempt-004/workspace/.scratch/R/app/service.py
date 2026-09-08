"""Write the public diagnostic projection and report logging failures."""

import json
import math

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


def _copy_scalars(source, names):
    result = {}
    for name in names:
        if name not in source:
            continue
        value = source[name]
        if value is None or type(value) in (str, bool, int):
            result[name] = value
        elif type(value) is float and math.isfinite(value):
            result[name] = value
    return result


def _public_record(record, depth=0, ancestors=None):
    # Unsupported objects never reach JSON's representation fallback.
    if type(record) is not dict:
        return {}
    if ancestors is None:
        ancestors = set()
    identity = id(record)
    if identity in ancestors:
        return {}
    ancestors.add(identity)
    try:
        result = _copy_scalars(record, ('correlation', 'message', 'code'))
        error = record.get('error')
        if type(error) is dict:
            result['error'] = _copy_scalars(error, ('type', 'code'))
        elif isinstance(error, BaseException):
            # Exception messages, arguments and repr may include private data.
            result['error'] = {'type': type(error).__name__}
        children = record.get('children')
        if type(children) in (list, tuple):
            result['children'] = []
            if depth < X06_MAX_DEPTH:
                result['children'] = [
                    _public_record(child, depth + 1, ancestors)
                    for child in children[:X06_MAX_CHILDREN]
                ]
        return result
    finally:
        ancestors.remove(identity)


def run(diagnostic_record, sink):
    try:
        line = json.dumps(_public_record(diagnostic_record), allow_nan=False)
        sink.write(line)
    except Exception:
        return 'log-error'
    return 'logged'
