"""Diagnostic serialization baseline."""
import json


def run(diagnostic_record, sink):
    if type(diagnostic_record) is dict:
        record = diagnostic_record.copy()
        if 'correlation' in record:
            value = record['correlation']
            if not (value is None or type(value) in (str, int, float, bool)):
                record['correlation'] = None
    else:
        record = {}

    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
