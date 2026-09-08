"""Decision service for concurrent operation simulation."""

from fixture_api.runtime import _x24_read, _x24_prepare


def _is_prepare_token(value):
    return (
        isinstance(value, tuple)
        and len(value) == 3
        and isinstance(value[2], int)
    )


def _normalize_prepare_group(value):
    if _is_prepare_token(value):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return None


def _commit(decision_store, value):
    prepare_tokens = _normalize_prepare_group(value)
    if not prepare_tokens:
        return 'conflict'

    touched_groups = set()
    staged = []
    for token in prepare_tokens:
        if not _is_prepare_token(token):
            return 'conflict'
        group, actor, revision = token
        rows = decision_store.rows
        if group not in rows or actor not in rows[group]:
            return 'conflict'
        if decision_store.revisions[group] != revision:
            return 'conflict'
        if not rows[group][actor]:
            return 'conflict'
        if group in touched_groups:
            return 'conflict'
        touched_groups.add(group)
        staged.append((group, actor))

    for group, actor in staged:
        decision_store.commit(group, actor)
    return 'committed'


def run(decision_store, operation, value):
    if operation == 'read':
        return _x24_read(decision_store, value)
    if operation == 'prepare':
        return _x24_prepare(decision_store, value)
    if operation == 'commit':
        return _commit(decision_store, value)
    raise ValueError(operation)
