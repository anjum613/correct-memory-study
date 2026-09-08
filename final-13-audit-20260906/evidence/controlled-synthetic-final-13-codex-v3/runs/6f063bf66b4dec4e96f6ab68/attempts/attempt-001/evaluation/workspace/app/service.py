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
        if not isinstance(value, tuple) or len(value) != 3:
            return 'conflict'
        group, actor, _revision = value
        if group not in decision_store.rows:
            return 'conflict'
        row = decision_store.rows[group]
        if actor not in row or not row[actor]:
            return 'conflict'

        after_rows = copy.deepcopy(decision_store.rows)
        after_rows[group][actor] = False
        if not all(any(row.values()) for row in after_rows.values()):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
