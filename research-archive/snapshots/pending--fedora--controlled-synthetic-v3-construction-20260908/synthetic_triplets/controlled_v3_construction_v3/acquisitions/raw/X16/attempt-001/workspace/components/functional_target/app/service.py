"""Bind sign-in to a fresh server session with limited state continuity."""

from copy import deepcopy


def run(session_store, operation, session_id, user=None):
    if operation == 'query':
        row = session_store.active(session_id)
        return None if row is None else row.get('user')
    if operation == 'logout':
        session_store.rows.pop(session_id, None)
        return 'signed-out'
    if operation != 'login' or user is None:
        return None

    previous = session_store.active(session_id)
    expires_at = session_store.now + session_store.lifetime
    transferred = {}
    if previous is not None:
        expires_at = previous.get('expires_at', expires_at)
        for field in ('cart', 'preferences'):
            if field in previous:
                transferred[field] = deepcopy(previous[field])

    # Identity and authority come exclusively from this sign-in, never from
    # client-nominated session state. Keep the original expiration deadline.
    transferred['user'] = user
    transferred['expires_at'] = expires_at
    token = session_store.fresh()
    if token == session_id or token in session_store.rows:
        return None
    session_store.rows[token] = transferred
    session_store.rows.pop(session_id, None)
    return token
