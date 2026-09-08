"""Write a safe, structured diagnostic record to a sink."""
import json
import math

from fixture_api.contracts import X06_MAX_CHILDREN, X06_MAX_DEPTH


def _value(value, depth=0, child_values=False):
    """Convert a diagnostic value to JSON data without losing its shape.

    Diagnostics are commonly assembled while handling another failure, so a
    malformed value must not prevent the rest of the record from being logged.
    The limits also make an accidentally recursive/very large diagnostic safe
    to write.
    """
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float:
        return value if math.isfinite(value) else None

    # Keep scalar details at the boundary, but do not descend into a fifth
    # level of containers.
    if depth >= X06_MAX_DEPTH:
        return None

    if type(value) is dict:
        result = {}
        for key, item in value.items():
            # JSON object names are strings.  Ignoring other keys avoids
            # json.dumps silently changing their identity.
            if type(key) is str:
                result[key] = _value(
                    item, depth + 1, key == 'children'
                )
        return result

    if type(value) is list:
        values = value[:X06_MAX_CHILDREN] if child_values else value
        return [_value(item, depth + 1) for item in values]

    # Match the old correlation behaviour for unsupported values: retain the
    # field as an explicit unavailable value rather than failing the log.
    return None


def run(diagnostic_record, sink):
    record = _value(diagnostic_record) if type(diagnostic_record) is dict else {}
    try:
        sink.write(json.dumps(record))
    except Exception:
        return 'log-error'
    return 'logged'
