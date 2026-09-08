"""Optimistic, invariant-preserving decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value

        # A decision is only useful if it can leave another actor active in
        # its group.  Include the record version so that this observation can
        # be checked when the caller later tries to commit it.
        if group not in decision_store.rows:
            return None
        if actor not in decision_store.rows[group]:
            return None
        if not decision_store.rows[group][actor]:
            return None
        if not any(
            active
            for other, active in decision_store.rows[group].items()
            if other != actor
        ):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        # The decision is an optimistic snapshot.  A change to its own group
        # invalidates that snapshot, but changes to other groups do not: their
        # invariants are independent and may safely proceed concurrently.
        if not isinstance(value, tuple) or len(value) != 3:
            return 'conflict'
        group, actor, revision = value
        if group not in decision_store.rows:
            return 'conflict'
        if actor not in decision_store.rows[group]:
            return 'conflict'
        if decision_store.revisions[group] != revision:
            return 'conflict'
        if not decision_store.rows[group][actor]:
            return 'conflict'
        if not any(
            active
            for other, active in decision_store.rows[group].items()
            if other != actor
        ):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
