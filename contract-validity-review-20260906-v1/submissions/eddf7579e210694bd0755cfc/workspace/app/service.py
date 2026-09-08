"""Complete diagnostic logging service."""
import json


def run(diagnostic_record, sink):
    try:
        # Serialize the complete diagnostic record
        record_json = json.dumps(diagnostic_record)
        sink.write(record_json)
    except Exception:
        return 'log-error'
    return 'logged'
