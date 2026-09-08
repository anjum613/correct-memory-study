"""Correlation-only diagnostic baseline."""
import json

def run(diagnostic_record, sink):
    try:
        # Serialize the complete diagnostic object
        sink.write(json.dumps(diagnostic_record))
    except Exception:
        return 'log-error'
    return 'logged'
