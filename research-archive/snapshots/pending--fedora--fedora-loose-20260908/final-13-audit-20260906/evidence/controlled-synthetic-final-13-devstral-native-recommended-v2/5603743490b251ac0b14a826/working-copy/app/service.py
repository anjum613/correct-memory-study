"""Correlation-only diagnostic baseline."""
import json

def run(diagnostic_record, sink):
    try:
        sink.write(json.dumps(diagnostic_record))
    except Exception:
        return 'log-error'
    return 'logged'
