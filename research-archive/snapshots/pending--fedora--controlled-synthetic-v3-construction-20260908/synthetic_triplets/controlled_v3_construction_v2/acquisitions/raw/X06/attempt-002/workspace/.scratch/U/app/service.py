"""Write complete diagnostics whose reachable fields are approved for logging."""
import json


def run(diagnostic_record, sink):
    try:
        sink.write(json.dumps(diagnostic_record, default=repr))
    except Exception:
        return 'log-error'
    return 'logged'
