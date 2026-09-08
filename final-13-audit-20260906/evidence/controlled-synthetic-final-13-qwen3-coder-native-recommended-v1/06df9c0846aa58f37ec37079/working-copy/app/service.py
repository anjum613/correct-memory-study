"""Concurrent decision implementation."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        # Check if the actor exists and is currently active
        if group not in decision_store.rows or actor not in decision_store.rows[group] or (not decision_store.rows[group][actor]):
            return None
        # Check if there would still be at least one active actor in this group after deactivation
        if not any((active for other, active in decision_store.rows[group].items() if other != actor)):
            return None
        # Return the preparation token with revision info
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        group, actor, revision = value
        # Check if this is a valid commit (revision matches current)
        if decision_store.revisions[group] != revision:
            return 'conflict'
        # Perform the actual commit
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
