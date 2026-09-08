"""Optimistic decisions coordinated over each complete invariant group."""
from copy import deepcopy


def _prepare(store, value):
    group, actor = value
    if group not in store.rows:
        return None
    row = store.rows[group]
    if actor not in row or not row[actor]:
        return None
    if not any(active for other, active in row.items() if other != actor):
        return None
    return (group, actor, store.revisions[group])


def run(decision_store, operation, value):
    store = decision_store
    if operation == 'read':
        return deepcopy(store.rows[value])
    if operation == 'prepare':
        return _prepare(store, value)
    if operation == 'commit':
        if value is None:
            return 'conflict'
        group, actor, revision = value
        if group not in store.rows or store.revisions[group] != revision:
            return 'conflict'
        # Validate the full safety condition again at the atomic commit boundary.
        if _prepare(store, (group, actor)) is None:
            return 'conflict'
        store.commit(group, actor)
        return 'committed'
    raise ValueError('unknown operation')
