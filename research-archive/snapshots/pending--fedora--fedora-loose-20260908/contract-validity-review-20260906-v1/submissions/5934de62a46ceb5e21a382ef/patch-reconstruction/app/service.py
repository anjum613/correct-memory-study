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
    # Preserve other public diagnostic fields
    for key in ('message', 'code', 'children', 'error'):
        if key in diagnostic_record:
            record[key] = diagnostic_record[key]
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
