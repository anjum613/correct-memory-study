"""Write the original correlation diagnostic to the operational sink."""
import json


def run(diagnostic_record, sink):
    record = {}
    if 'correlation' in diagnostic_record:
        record['correlation'] = diagnostic_record['correlation']
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
