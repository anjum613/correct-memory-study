"""Concurrent decisions implementation."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        # Check if the actor exists and is active (True)
        if group not in decision_store.rows or actor not in decision_store.rows[group] or (not decision_store.rows[group][actor]):
            return None
        # Check if there's at least one other active actor in the same group
        if not any((active for other, active in decision_store.rows[group].items() if other != actor)):
            return None
        # Return the prepare result with revision info
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        group, actor, revision = value
        # Check if this is still a valid commit (revision hasn't changed)
        if revision != decision_store.revisions[group]:
            return 'conflict'
        # Perform the commit
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
