"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    record = {}
    if type(diagnostic_record) is dict:
        # Keep the diagnostic object's established shape intact.  Make a
        # shallow copy so normalising the legacy correlation field cannot
        # alter the object supplied by the caller; nested diagnostics remain
        # part of the serialized record.
        record = dict(diagnostic_record)
        if 'correlation' in record:
            value = record['correlation']
            if value is None or type(value) in (str, int, float, bool):
                record['correlation'] = value
            else:
                record['correlation'] = None
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
