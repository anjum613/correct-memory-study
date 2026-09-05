"""Case-sensitive Unicode handles with a single NFC identity relation."""
import unicodedata


_UNICODE_VERSION = '15.0.0'


def _valid(handle):
    return (isinstance(handle, str) and 1 <= len(handle) <= 32
            and all(c in '_-' or unicodedata.category(c)[0] in 'LMN'
                    for c in handle))


def _key(handle):
    return unicodedata.normalize('NFC', handle)


def _bindings(rows, canonical):
    # Scan the actual bindings, including legacy unnormalized keys. A secondary
    # index alone would miss collisions already present in an imported registry.
    return [raw for raw in rows
            if isinstance(raw, str) and _key(raw) == canonical]


def run(registry, operation, handle, argument=None):
    if unicodedata.unidata_version != _UNICODE_VERSION:
        raise RuntimeError('Unicode 15.0.0 is required')
    if not _valid(handle):
        return 'invalid'
    canonical = _key(handle)
    bindings = _bindings(registry.rows, canonical)
    if len(bindings) > 1:
        return 'ambiguous'
    if operation == 'register':
        if bindings:
            return 'exists'
        registry.rows[canonical] = {'owner': argument, 'display': handle}
        return 'registered'
    if operation == 'lookup':
        return registry.rows[bindings[0]]['owner'] if bindings else None
    if operation == 'rename':
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return 'invalid'
        owner, new_handle = argument
        if not _valid(new_handle):
            return 'invalid'
        if not bindings or registry.rows[bindings[0]]['owner'] != owner:
            return 'denied'
        new_key = _key(new_handle)
        destinations = _bindings(registry.rows, new_key)
        if len(destinations) > 1:
            return 'ambiguous'
        if destinations:
            return 'exists'
        old_key = bindings[0]
        renamed = dict(registry.rows[old_key])
        renamed['display'] = new_handle
        del registry.rows[old_key]
        registry.rows[new_key] = renamed
        return 'renamed'
    raise ValueError('unknown operation')
