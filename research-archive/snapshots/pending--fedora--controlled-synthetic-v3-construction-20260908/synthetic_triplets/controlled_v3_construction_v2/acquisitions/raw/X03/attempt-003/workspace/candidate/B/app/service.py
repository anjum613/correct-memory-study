"""Handle registration with exact, case-sensitive ASCII identity."""
from fixture_api import contracts as k


def _valid(handle):
    return (
        isinstance(handle, str)
        and k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH
        and all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
                for c in handle)
    )


def run(registry, operation, handle, argument=None):
    if not _valid(handle):
        return "invalid"
    if operation == "register":
        if handle in registry.rows:
            return "exists"
        registry.rows[handle] = {"owner": argument, "display": handle}
        return "registered"
    if operation == "lookup":
        row = registry.rows.get(handle)
        return None if row is None else row["owner"]
    if operation == "rename":
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return "invalid"
        owner, new_handle = argument
        if not _valid(new_handle):
            return "invalid"
        row = registry.rows.get(handle)
        if row is None:
            return "missing"
        if row["owner"] != owner:
            return "forbidden"
        if new_handle != handle and new_handle in registry.rows:
            return "exists"
        replacement = dict(row, display=new_handle)
        del registry.rows[handle]
        registry.rows[new_handle] = replacement
        return "renamed"
    return "invalid"
