"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    record = diagnostic_record.copy() if isinstance(diagnostic_record, dict) else {}
    if type(diagnostic_record) is dict and 'correlation' in diagnostic_record:
        value = diagnostic_record['correlation']
        if value is None or type(value) in (str, int, float, bool):
            record['correlation'] = value
        else:
            record['correlation'] = None
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
