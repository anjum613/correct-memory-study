"""ASCII-only handle registration and resolution."""


def _valid(handle):
    return (isinstance(handle, str) and 1 <= len(handle) <= 32
            and all('a' <= c <= 'z' or 'A' <= c <= 'Z'
                    or '0' <= c <= '9' or c in '_-' for c in handle))


def run(registry, operation, handle, argument=None):
    if not _valid(handle):
        return 'invalid'
    if operation == 'register':
        if handle in registry.rows:
            return 'exists'
        registry.rows[handle] = {'owner': argument, 'display': handle}
        return 'registered'
    if operation == 'lookup':
        row = registry.rows.get(handle)
        return None if row is None else row['owner']
    if operation == 'rename':
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return 'invalid'
        owner, new_handle = argument
        if not _valid(new_handle):
            return 'invalid'
        row = registry.rows.get(handle)
        if row is None or row['owner'] != owner:
            return 'denied'
        if new_handle in registry.rows:
            return 'exists'
        renamed = dict(row)
        renamed['display'] = new_handle
        del registry.rows[handle]
        registry.rows[new_handle] = renamed
        return 'renamed'
    raise ValueError('unknown operation')
