"""Full diagnostic retention service."""

import json


def run(diagnostic_record, sink):
    # Preserve all fields from the diagnostic record
    record = diagnostic_record.copy() if isinstance(diagnostic_record, dict) else {}
    
    # Ensure correlation is handled properly (maintaining backward compatibility)
    if "correlation" in record:
        correlation = record["correlation"]
        if correlation is not None and not isinstance(correlation, (str, int, float, bool)):
            record["correlation"] = None
    
    try:
        sink.write(json.dumps(record))
    except Exception:
        return "log-error"
    return "logged"
