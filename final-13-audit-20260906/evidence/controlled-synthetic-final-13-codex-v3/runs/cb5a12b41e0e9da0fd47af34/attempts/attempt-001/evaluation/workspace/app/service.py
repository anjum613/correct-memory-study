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
        if not any(active for other, active in decision_store.rows[group].items() if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        if value is None:
            return 'conflict'
        group, actor, _revision = value
        if group not in decision_store.rows:
            return 'conflict'
        if actor not in decision_store.rows[group]:
            return 'conflict'
        if not decision_store.rows[group][actor]:
            return 'conflict'

        updated_rows = copy.deepcopy(decision_store.rows)
        updated_rows[group][actor] = False
        if not all(any(row.values()) for row in updated_rows.values()):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
