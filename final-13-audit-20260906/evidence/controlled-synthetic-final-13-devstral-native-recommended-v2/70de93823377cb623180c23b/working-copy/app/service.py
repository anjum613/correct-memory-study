"""Diagnostic logger with correlation and structured fields."""
import json


def run(diagnostic_record, sink):
    # Create a copy of the record to avoid modifying the input
    record = {}
    
    # Handle the correlation field specifically
    if isinstance(diagnostic_record, dict) and 'correlation' in diagnostic_record:
        value = diagnostic_record['correlation']
        if value is None or isinstance(value, (str, int, float, bool)):
            record['correlation'] = value
        else:
            record['correlation'] = None
    
    # Copy other fields while preserving structure
    for key, value in diagnostic_record.items():
        if key != 'correlation':
            record[key] = value
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
