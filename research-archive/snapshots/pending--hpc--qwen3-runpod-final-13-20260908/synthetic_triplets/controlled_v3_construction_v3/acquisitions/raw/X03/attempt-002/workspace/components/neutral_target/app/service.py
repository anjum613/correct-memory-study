"""Case-sensitive ASCII handle registry."""


def _valid(handle):
    return (
        isinstance(handle, str)
        and 1 <= len(handle) <= 32
        and handle.isascii()
        and all(c.isalnum() or c in '_-' for c in handle)
    )


def run(registry, operation, handle, argument=None):
    if not _valid(handle):
        return 'invalid'
    rows = registry.rows
    if operation == 'register':
        if handle in rows:
            return 'exists'
        rows[handle] = {'owner': argument, 'display': handle}
        return 'registered'
    if operation == 'lookup':
        row = rows.get(handle)
        return None if row is None else row['owner']
    if operation == 'rename':
        owner, destination = argument
        if not _valid(destination):
            return 'invalid'
        if handle not in rows or rows[handle]['owner'] != owner:
            return 'denied'
        if destination in rows and destination != handle:
            return 'exists'
        row = dict(rows[handle])
        row['display'] = destination
        del rows[handle]
        rows[destination] = row
        return 'renamed'
    raise ValueError('unknown operation')
