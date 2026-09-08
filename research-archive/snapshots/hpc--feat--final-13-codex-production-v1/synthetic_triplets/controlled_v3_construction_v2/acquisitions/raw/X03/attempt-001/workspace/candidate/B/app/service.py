"""Case-sensitive handle registration under the ASCII source policy."""
from fixture_api import contracts as k


def _valid(handle):
    return (
        isinstance(handle, str)
        and k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH
        and all(
            "a" <= char <= "z" or "A" <= char <= "Z"
            or "0" <= char <= "9" or char in "_-"
            for char in handle
        )
    )


def run(registry, operation, handle, argument=None):
    if not _valid(handle):
        return "invalid"
    rows = registry.rows
    if operation == "register":
        if handle in rows:
            return "exists"
        rows[handle] = {"owner": argument, "display": handle}
        return "registered"
    if operation == "lookup":
        row = rows.get(handle)
        return None if row is None else row["owner"]
    if operation == "rename":
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return "invalid"
        owner, replacement = argument
        if not _valid(replacement):
            return "invalid"
        if handle not in rows:
            return "missing"
        if rows[handle]["owner"] != owner:
            return "forbidden"
        if replacement != handle and replacement in rows:
            return "exists"
        row = dict(rows[handle])
        row["display"] = replacement
        del rows[handle]
        rows[replacement] = row
        return "renamed"
    return "invalid"
