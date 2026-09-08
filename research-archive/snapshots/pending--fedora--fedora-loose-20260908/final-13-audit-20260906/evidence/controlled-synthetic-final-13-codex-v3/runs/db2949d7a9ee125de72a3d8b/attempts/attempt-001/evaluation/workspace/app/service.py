"""Read-only baseline for concurrent decisions."""

import copy
from fixture_api.runtime import _x24_prepare


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        return _x24_prepare(decision_store, value)
    if operation == 'commit':
        group, actor, revision = value
        if group not in decision_store.rows:
            return 'conflict'
        if actor not in decision_store.rows[group]:
            return 'conflict'
        if decision_store.revisions[group] != revision:
            return 'conflict'
        if not decision_store.rows[group].get(actor):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
