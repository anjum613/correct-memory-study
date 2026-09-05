"""Write diagnostics whose reachable fields are approved for the log."""
import json


def run(diagnostic_record, sink):
    sink.write(json.dumps(diagnostic_record, default=repr))
    return 'logged'
