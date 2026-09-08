"""Case-sensitive ASCII handle registration and exact resolution."""


def _valid(handle):
    return (
        isinstance(handle, str)
        and 1 <= len(handle) <= 32
        and all(
            'A' <= character <= 'Z'
            or 'a' <= character <= 'z'
            or '0' <= character <= '9'
            or character in '_-'
            for character in handle
        )
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
        return rows[handle]['owner'] if handle in rows else None
    if operation == 'rename':
        if not isinstance(argument, (tuple, list)) or len(argument) != 2:
            return 'invalid'
        owner, new_handle = argument
        if not _valid(new_handle):
            return 'invalid'
        if handle not in rows or rows[handle]['owner'] != owner:
            return 'forbidden'
        if new_handle != handle and new_handle in rows:
            return 'exists'
        replacement = dict(rows[handle])
        replacement['display'] = new_handle
        del rows[handle]
        rows[new_handle] = replacement
        return 'renamed'
    return 'invalid'
