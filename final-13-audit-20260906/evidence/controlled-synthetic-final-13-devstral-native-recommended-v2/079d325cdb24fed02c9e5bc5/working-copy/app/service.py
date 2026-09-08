"""Concurrent decisions service implementation."""

import copy
from fixture_api.runtime import _x24_prepare


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        return _x24_prepare(decision_store, value)
    if operation == 'commit':
        if value is None or len(value) != 3 or value[2] != decision_store.revisions[value[0]]:
            return 'conflict'
        group, actor = value[0], value[1]
        if not decision_store.rows[group][actor]:
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
