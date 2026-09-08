"""Serialize only the documented public diagnostic projection."""
import json


MAX_DEPTH = 4
MAX_CHILDREN = 8


def _scalar(value):
    # Exact built-in types prevent serializer and representation callbacks.
    if value is None or type(value) in (str, int, float, bool):
        return value
    return None


def _project(record, depth, ancestors):
    if type(record) is not dict or id(record) in ancestors:
        return {}
    ancestors.add(id(record))
    try:
        public = {}
        for field in ('correlation', 'message', 'code'):
            if field in record:
                public[field] = _scalar(record[field])
        if 'error' in record:
            error = record['error']
            if type(error) is dict:
                public['error'] = {
                    field: _scalar(error[field])
                    for field in ('type', 'code') if field in error
                }
            else:
                # Neither exception text nor arbitrary object repr is public.
                public['error'] = {}
        if 'children' in record:
            children = record['children']
            public['children'] = []
            if depth < MAX_DEPTH and type(children) in (list, tuple):
                public['children'] = [
                    _project(child, depth + 1, ancestors)
                    for child in children[:MAX_CHILDREN]
                ]
        return public
    finally:
        ancestors.remove(id(record))


def run(diagnostic_record, sink):
    try:
        public = _project(diagnostic_record, 0, set())
        sink.write(json.dumps(public))
    except Exception:
        # Failure objects can embed the original confidential record. Never
        # log them or retry by serializing the unfiltered input.
        return 'log-error'
    return 'logged'
