"""Full diagnostic record handler."""
import json


def run(diagnostic_record, sink):
    # Preserve all fields from diagnostic_record
    record = diagnostic_record.copy() if isinstance(diagnostic_record, dict) else {}
    
    # Ensure correlation field is properly handled if present
    if 'correlation' in record:
        value = record['correlation']
        if value is not None and type(value) not in (str, int, float, bool):
            record['correlation'] = None
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
