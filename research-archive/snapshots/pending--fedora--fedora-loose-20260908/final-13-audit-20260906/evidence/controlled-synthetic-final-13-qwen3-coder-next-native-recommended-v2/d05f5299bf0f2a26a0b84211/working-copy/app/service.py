"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    record = {}
    if type(diagnostic_record) is dict and 'correlation' in diagnostic_record:
        value = diagnostic_record['correlation']
        if value is None or type(value) in (str, int, float, bool):
            record['correlation'] = value
        else:
            record['correlation'] = None
    
    # Preserve all other fields from the diagnostic record
    if type(diagnostic_record) is dict:
        for key, value in diagnostic_record.items():
            if key != 'correlation':
                record[key] = value
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
