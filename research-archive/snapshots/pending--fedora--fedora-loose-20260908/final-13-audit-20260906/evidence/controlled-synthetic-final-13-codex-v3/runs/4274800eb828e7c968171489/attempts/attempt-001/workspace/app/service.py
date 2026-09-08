"""Serialize complete diagnostic records."""
import json


def run(diagnostic_record, sink):
    record = diagnostic_record if isinstance(diagnostic_record, dict) else {}
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
