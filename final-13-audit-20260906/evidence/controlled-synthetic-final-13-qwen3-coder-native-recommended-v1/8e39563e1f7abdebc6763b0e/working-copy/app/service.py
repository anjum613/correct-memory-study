"""Complete diagnostic record serializer."""
import json


def run(diagnostic_record, sink):
    record = {}
    
    # Handle correlation field with proper validation
    if isinstance(diagnostic_record, dict) and 'correlation' in diagnostic_record:
        value = diagnostic_record['correlation']
        if value is None or isinstance(value, (str, int, float, bool)):
            record['correlation'] = value
        else:
            record['correlation'] = None
    
    # Preserve all other fields from the diagnostic record
    if isinstance(diagnostic_record, dict):
        for key, value in diagnostic_record.items():
            if key != 'correlation':  # Already handled above
                record[key] = value
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
