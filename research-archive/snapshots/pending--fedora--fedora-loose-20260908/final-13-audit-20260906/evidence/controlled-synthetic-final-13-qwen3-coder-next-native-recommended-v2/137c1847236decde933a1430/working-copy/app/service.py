"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        # Check if actor exists and is active
        if group not in decision_store.rows or actor not in decision_store.rows[group]:
            return None
        if not decision_store.rows[group][actor]:
            return None
        # Check if there's another active actor in the same group (invariant)
        if not any(active for other, active in decision_store.rows[group].items() if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        # value is the decision tuple from prepare: (group, actor, revision)
        if value is None:
            return 'conflict'
        group, actor, expected_revision = value
        # Check if the decision is still valid (revision hasn't changed)
        if decision_store.revisions[group] != expected_revision:
            return 'conflict'
        # Apply the commit
        decision_store.rows[group][actor] = False
        decision_store.revisions[group] += 1
        decision_store.events.append(('commit', group, actor))
        return 'committed'
    raise ValueError(operation)
