"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        if group not in decision_store.rows:
            return None
        row = decision_store.rows[group]
        if actor not in row or not row[actor]:
            return None
        if not any(active for other, active in row.items() if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        group, actor, _revision = value
        if group not in decision_store.rows:
            return 'conflict'
        row = decision_store.rows[group]
        if actor not in row or not row[actor]:
            return 'conflict'
        if not any(active for other, active in row.items() if other != actor):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
