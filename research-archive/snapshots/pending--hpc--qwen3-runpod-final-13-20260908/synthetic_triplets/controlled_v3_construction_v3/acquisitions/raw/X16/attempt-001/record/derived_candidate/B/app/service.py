"""Session query and sign-out baseline; sign-in is unavailable."""


def run(session_store, operation, session_id, user=None):
    if operation == 'query':
        row = session_store.active(session_id)
        return None if row is None else row.get('user')
    if operation == 'logout':
        session_store.rows.pop(session_id, None)
        return 'signed-out'
    return None
