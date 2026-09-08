"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    try:
        # Serialize the complete diagnostic object
        record_json = json.dumps(diagnostic_record)
        sink.write(record_json)
    except Exception:
        return 'log-error'
    return 'logged'
