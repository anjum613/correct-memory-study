"""Complete diagnostic retention service."""
import json


def run(diagnostic_record, sink):
    record = {}
    if type(diagnostic_record) is dict:
        # Preserve all fields from the diagnostic record
        record = diagnostic_record.copy()
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
