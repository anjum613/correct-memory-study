"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        if group not in decision_store.rows:
            return None
        if actor not in decision_store.rows[group]:
            return None
        if not decision_store.rows[group][actor]:
            return None

        rows = copy.deepcopy(decision_store.rows)
        rows[group][actor] = False
        if not all(any(row.values()) for row in rows.values()):
            return None

        return (group, actor)
    if operation == 'commit':
        group, actor = value
        if group not in decision_store.rows:
            return 'conflict'
        if actor not in decision_store.rows[group]:
            return 'conflict'
        if not decision_store.rows[group][actor]:
            return 'conflict'

        rows = copy.deepcopy(decision_store.rows)
        rows[group][actor] = False
        if not all(any(row.values()) for row in rows.values()):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
