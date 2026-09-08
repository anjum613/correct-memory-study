"""Read-only baseline for concurrent decisions."""

import copy
from fixture_api import runtime


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        return runtime._x24_prepare(decision_store, value)
    if operation == 'commit':
        if value is None:
            return 'conflict'
        group, actor, expected_revision = value
        if decision_store.revisions[group] != expected_revision:
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
