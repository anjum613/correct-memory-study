"""Optimistic decisions validated over the entire invariant group."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])

    if operation == 'prepare':
        group, actor = value
        if group not in decision_store.rows:
            return None
        revision = decision_store.revisions[group]
        row = decision_store.rows[group]
        if actor not in row or not row[actor]:
            return None
        if not any(active for other, active in row.items() if other != actor):
            return None
        return (group, actor, revision)

    if operation == 'commit':
        if value is None:
            return 'conflict'
        group, actor, revision = value
        if group not in decision_store.rows:
            return 'conflict'
        # Every actor in this group participates in the same invariant.
        # A changed group must be prepared again against its new state.
        if decision_store.revisions[group] != revision:
            return 'conflict'
        row = decision_store.rows[group]
        if actor not in row or not row[actor]:
            return 'conflict'
        if not any(active for other, active in row.items() if other != actor):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'

    raise ValueError(operation)
