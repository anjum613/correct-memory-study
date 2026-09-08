"""Write approved diagnostic objects to the operational log."""

import json


def run(diagnostic_record, sink):
    line = json.dumps(diagnostic_record, default=repr)
    sink.write(line)
    return 'logged'
