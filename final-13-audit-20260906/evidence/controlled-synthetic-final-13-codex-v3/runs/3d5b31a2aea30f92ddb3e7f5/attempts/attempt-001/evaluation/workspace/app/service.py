"""Operational logging service."""
import json


def run(diagnostic_record, sink):
    if type(diagnostic_record) is dict:
        record = dict(diagnostic_record)
        if 'correlation' in record:
            value = record['correlation']
            if value is None or type(value) in (str, int, float, bool):
                record['correlation'] = value
            else:
                record['correlation'] = None
    else:
        record = {}

    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
