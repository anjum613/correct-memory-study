"""Service entrypoint for concurrent multi-record decision operations."""

from fixture_api import runtime


def _is_prepare_pair(value):
    return isinstance(value, tuple) and len(value) == 2 and all(
        isinstance(part, str) for part in value
    )


def _is_commit_token(value):
    return isinstance(value, tuple) and len(value) == 3 and isinstance(value[2], int)


def _as_batch(value):
    if isinstance(value, list):
        return list(value)
    if _is_prepare_pair(value):
        return [value]
    if _is_commit_token(value):
        return [value]
    if isinstance(value, tuple):
        return list(value)
    return [value]


def run(decision_store, operation, value):
    if operation == 'read':
        return runtime._x24_read(decision_store, value)

    if operation == 'prepare':
        prepared = []
        for item in _as_batch(value):
            token = runtime._x24_prepare(decision_store, item)
            if token is None:
                return None
            prepared.append(token)
        if len(prepared) == 1:
            return prepared[0]
        return tuple(prepared)

    if operation == 'commit':
        updates = _as_batch(value)
        if not updates:
            return 'committed'

        lock_tokens = []
        seen_pairs = set()
        for token in updates:
            if not _is_commit_token(token):
                return 'conflict'

            group, actor, revision = token
            if (group, actor) in seen_pairs:
                return 'conflict'
            seen_pairs.add((group, actor))

            if (
                group not in decision_store.revisions
                or actor not in decision_store.rows[group]
                or revision != decision_store.revisions[group]
                or not decision_store.rows[group][actor]
            ):
                return 'conflict'

            lock_tokens.append((group, actor))

        for group, actor in lock_tokens:
            decision_store.commit(group, actor)
        return 'committed'

    raise ValueError(operation)
