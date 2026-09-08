"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    record = {}
    
    # Copy all fields from diagnostic_record to record
    if isinstance(diagnostic_record, dict):
        record = diagnostic_record.copy()
    
    # Ensure correlation field is handled properly (existing behavior)
    if 'correlation' in record:
        value = record['correlation']
        if value is None or type(value) in (str, int, float, bool):
            record['correlation'] = value
        else:
            record['correlation'] = None
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
