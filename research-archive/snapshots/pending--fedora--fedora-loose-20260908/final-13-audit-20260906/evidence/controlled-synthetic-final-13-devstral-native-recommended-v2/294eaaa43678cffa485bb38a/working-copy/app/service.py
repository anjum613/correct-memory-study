"""Correlation-only diagnostic baseline."""
import json


def run(diagnostic_record, sink):
    # Preserve all fields from the diagnostic record
    record = {}
    if type(diagnostic_record) is dict:
        for key, value in diagnostic_record.items():
            # Only include fields with primitive values or nested dictionaries/lists
            if isinstance(value, (str, int, float, bool, dict, list)) or value is None:
                record[key] = value
            else:
                record[key] = None
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
