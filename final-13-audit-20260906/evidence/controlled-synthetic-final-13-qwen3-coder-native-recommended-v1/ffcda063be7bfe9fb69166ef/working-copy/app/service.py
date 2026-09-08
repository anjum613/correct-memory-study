"""Concurrent decision making with multi-record safety."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    elif operation == 'prepare':
        group, actor = value
        # Check if actor exists and is active
        if group not in decision_store.rows or actor not in decision_store.rows[group] or not decision_store.rows[group][actor]:
            return None
        # Check if there's at least one other active actor in the same group
        active_count = sum(1 for k, v in decision_store.rows[group].items() if k != actor and v)
        if active_count == 0:
            return None
        # Return preparation info (group, actor, revision)
        return (group, actor, decision_store.revisions[group])
    elif operation == 'commit':
        if value is None:
            return 'conflict'
        group, actor, revision = value
        # Validate commit against current state
        if group not in decision_store.rows or actor not in decision_store.rows[group] or not decision_store.rows[group][actor]:
            return 'conflict'
        if decision_store.revisions[group] != revision:
            return 'conflict'
        # Perform actual commit
        decision_store.commit(group, actor)
        return 'committed'
    else:
        raise ValueError(operation)
