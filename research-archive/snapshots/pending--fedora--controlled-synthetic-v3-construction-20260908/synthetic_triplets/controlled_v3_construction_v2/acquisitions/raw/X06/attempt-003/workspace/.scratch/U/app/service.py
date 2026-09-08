"""Write complete diagnostics and handle logging failures."""
import json


def run(diagnostic_record, sink):
    try:
        try:
            line = json.dumps(diagnostic_record, default=repr)
        except Exception:
            line = json.dumps({'diagnostic': repr(diagnostic_record)})
        sink.write(line)
    except Exception:
        return 'log-error'
    return 'logged'
