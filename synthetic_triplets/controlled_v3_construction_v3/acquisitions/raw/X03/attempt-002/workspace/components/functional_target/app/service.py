"""Case-sensitive Unicode 15.0 handles with NFC identity equivalence."""

import unicodedata


def _valid(handle):
    return (
        isinstance(handle, str)
        and 1 <= len(handle) <= 32
        and all(
            c in '_-' or unicodedata.category(c)[0] in {'L', 'M', 'N'}
            for c in handle
        )
    )


def _matches(rows, identity):
    # Scan existing bindings as well as newly canonicalized keys. Old rows
    # may have been created with a noncanonical spelling.
    return [
        key for key in rows
        if isinstance(key, str)
        and unicodedata.normalize('NFC', key) == identity
    ]


def run(registry, operation, handle, argument=None):
    if unicodedata.unidata_version != '15.0.0':
        raise RuntimeError('Unicode 15.0.0 is required')
    if not _valid(handle):
        return 'invalid'
    rows = registry.rows
    identity = unicodedata.normalize('NFC', handle)
    matches = _matches(rows, identity)
    if operation == 'register':
        if matches:
            return 'exists'
        rows[identity] = {'owner': argument, 'display': handle}
        return 'registered'
    if operation == 'lookup':
        # Even an exact spelling must not select one of multiple bindings.
        if len(matches) != 1:
            return None
        return rows[matches[0]]['owner']
    if operation == 'rename':
        owner, destination = argument
        if not _valid(destination):
            return 'invalid'
        if len(matches) != 1 or rows[matches[0]]['owner'] != owner:
            return 'denied'
        destination_identity = unicodedata.normalize('NFC', destination)
        destination_matches = _matches(rows, destination_identity)
        source_key = matches[0]
        if any(key != source_key for key in destination_matches):
            return 'exists'
        # Validate ownership and collisions before touching the registry.
        row = dict(rows[source_key])
        row['display'] = destination
        del rows[source_key]
        rows[destination_identity] = row
        return 'renamed'
    raise ValueError('unknown operation')
