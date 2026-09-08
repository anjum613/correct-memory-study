"""Concurrent decisions with multi-record invariant."""

import copy
from fixture_api.runtime import _x24_read, _x24_prepare


def run(decision_store, operation, value):
    if operation == 'read':
        return _x24_read(decision_store, value)
    if operation == 'prepare':
        return _x24_prepare(decision_store, value)
    if operation == 'commit':
        if not isinstance(value, tuple) or len(value) != 3:
            return 'conflict'
        group, actor, revision = value
        if (decision_store.revisions[group] != revision or
            not decision_store.rows[group].get(actor, False)):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
