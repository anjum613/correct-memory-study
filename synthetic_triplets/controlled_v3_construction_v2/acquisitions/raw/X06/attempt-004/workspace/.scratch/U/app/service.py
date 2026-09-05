"""Write approved diagnostic objects and report logging failures."""

import json


def run(diagnostic_record, sink):
    try:
        line = json.dumps(diagnostic_record, default=repr)
        sink.write(line)
    except Exception:
        return 'log-error'
    return 'logged'
