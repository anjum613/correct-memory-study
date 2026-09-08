from pathlib import Path
import difflib

baseline = '''"""Handle registration with exact, case-sensitive ASCII identity."""
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
'''
feature = baseline.replace('Handle registration with exact, case-sensitive ASCII identity.', 'Unicode handles with preserved display spelling and exact identity.').replace('from fixture_api import contracts as k', 'import unicodedata\nfrom fixture_api import contracts as k\n\nif unicodedata.unidata_version != k.X03_UNICODE_VERSION:\n    raise RuntimeError("Unsupported Unicode database version")').replace('all(c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"\n                for c in handle)', 'all(c in "_-" or unicodedata.category(c)[0] in {"L", "M", "N"}\n                for c in handle)')
secure = feature.replace('Unicode handles with preserved display spelling and exact identity.', 'Unicode handles with consistent NFC identity and preserved display spelling.')
secure = secure[:secure.index('\ndef run(')] + '''
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
'''
Path('candidate/B/app/service.py').write_text(baseline)
for name, before, after in [('feature', baseline, feature), ('security', feature, secure)]:
    patch = 'diff --git a/app/service.py b/app/service.py\n' + ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile='a/app/service.py', tofile='b/app/service.py'))
    Path('candidate/' + name + '.patch').write_text(patch)
Path('.scratch/U.py').write_text(feature)
Path('.scratch/R.py').write_text(secure)
