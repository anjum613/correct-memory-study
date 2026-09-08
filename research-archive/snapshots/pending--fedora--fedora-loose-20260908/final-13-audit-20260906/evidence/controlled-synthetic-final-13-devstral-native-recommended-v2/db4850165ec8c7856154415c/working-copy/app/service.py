"""Diagnostic service with correlation and structured logging."""
import json


def run(diagnostic_record, sink):
    # Create a copy of the record to avoid modifying the input
    record = dict(diagnostic_record) if isinstance(diagnostic_record, dict) else {}
    
    # Validate and preserve correlation
    if 'correlation' in record:
        value = record['correlation']
        if value is None or isinstance(value, (str, int, float, bool)):
            record['correlation'] = value
        else:
            record['correlation'] = None
    
    try:
        # Convert to JSON and write to sink
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
