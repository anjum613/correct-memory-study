"""Case-sensitive NFC identities with original display spelling."""
import unicodedata

from fixture_api import contracts as k


def _valid(handle):
    return (
        unicodedata.unidata_version == k.X03_UNICODE_VERSION
        and isinstance(handle, str)
        and k.X03_MIN_LENGTH <= len(handle) <= k.X03_MAX_LENGTH
        and all(
            char in "_-" or unicodedata.category(char)[0] in {"L", "M", "N"}
            for char in handle
        )
    )


def _key(handle):
    return unicodedata.normalize("NFC", handle)


def _bindings(rows, handle):
    identity = _key(handle)
    return [stored for stored in rows if _key(stored) == identity]


def run(registry, operation, handle, argument=None):
    if not _valid(handle):
        return "invalid"
    rows = registry.rows
    bindings = _bindings(rows, handle)
    # Never choose an owner from ambiguous legacy bindings.
    if len(bindings) > 1:
        return "invalid"
    if operation == "register":
        if bindings:
            return "exists"
        rows[_key(handle)] = {"owner": argument, "display": handle}
        return "registered"
    if operation == "lookup":
        return rows[bindings[0]]["owner"] if bindings else None
    if operation == "rename":
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return "invalid"
        owner, replacement = argument
        if not _valid(replacement):
            return "invalid"
        if not bindings:
            return "missing"
        source = bindings[0]
        if rows[source]["owner"] != owner:
            return "forbidden"
        destinations = _bindings(rows, replacement)
        if len(destinations) > 1:
            return "invalid"
        if destinations and destinations[0] != source:
            return "exists"
        row = dict(rows[source])
        row["display"] = replacement
        del rows[source]
        rows[_key(replacement)] = row
        return "renamed"
    return "invalid"
