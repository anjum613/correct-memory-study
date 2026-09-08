"""Decision service with optimistic, per-record concurrency control."""

import copy

from fixture_api.runtime import _x24_prepare, _x24_read


def run(decision_store, operation, value):
    if operation == 'read':
        return _x24_read(decision_store, value)
    if operation == 'prepare':
        return _x24_prepare(decision_store, value)
    if operation == 'commit':
        if (not isinstance(value, tuple)) or len(value) != 3:
            return 'conflict'

        group, actor, revision = value
        if (group not in decision_store.rows or
                actor not in decision_store.rows[group] or
                decision_store.revisions.get(group) != revision or
                not decision_store.rows[group][actor] or
                not any(decision_store.rows[group][other]
                        for other in decision_store.rows[group]
                        if other != actor)):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
