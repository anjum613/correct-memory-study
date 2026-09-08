"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    record = {}
    if isinstance(diagnostic_record, dict):
        value = dict.get(diagnostic_record, 'correlation')
        if type(value) in (str, int, float, bool) or value is None:
            if 'correlation' in diagnostic_record:
                record['correlation'] = value
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
