"""Concurrent decision implementation."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        # Check if the actor is active in the group
        if group not in decision_store.rows or actor not in decision_store.rows[group] or (not decision_store.rows[group][actor]):
            return None
        # Check if there are other active actors
        if not any((active for other, active in decision_store.rows[group].items() if other != actor)):
            return None
        # Return transaction token with revision number
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        # Handle conflict checking
        group, actor, revision = value
        # Check if revision matches current revision
        if revision != decision_store.revisions[group]:
            return 'conflict'
        # Apply the commit
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
