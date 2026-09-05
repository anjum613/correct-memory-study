"""Unicode handles with consistent NFC identity and preserved display spelling."""
import unicodedata
from fixture_api import contracts as k

if unicodedata.unidata_version != k.X03_UNICODE_VERSION:
    raise RuntimeError("Unsupported Unicode database version")


def _valid(handle):
    return (
        isinstance(handle, str)
        and k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH
        and all(c in "_-" or unicodedata.category(c)[0] in {"L", "M", "N"}
                for c in handle)
    )


def _bindings(rows, handle):
    """Resolve all existing spellings, including legacy raw-key entries."""
    identity = unicodedata.normalize("NFC", handle)
    return [key for key in rows
            if isinstance(key, str)
            and unicodedata.normalize("NFC", key) == identity]


def run(registry, operation, handle, argument=None):
    if not _valid(handle):
        return "invalid"
    if operation == "register":
        if _bindings(registry.rows, handle):
            return "exists"
        registry.rows[handle] = {"owner": argument, "display": handle}
        return "registered"
    if operation == "lookup":
        matches = _bindings(registry.rows, handle)
        if len(matches) != 1:
            return None
        return registry.rows[matches[0]]["owner"]
    if operation == "rename":
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return "invalid"
        owner, new_handle = argument
        if not _valid(new_handle):
            return "invalid"
        matches = _bindings(registry.rows, handle)
        if not matches:
            return "missing"
        if len(matches) != 1:
            return "ambiguous"
        old_key = matches[0]
        row = registry.rows[old_key]
        if row["owner"] != owner:
            return "forbidden"
        destinations = _bindings(registry.rows, new_handle)
        if any(key != old_key for key in destinations):
            return "exists"
        replacement = dict(row, display=new_handle)
        del registry.rows[old_key]
        registry.rows[new_handle] = replacement
        return "renamed"
    return "invalid"
