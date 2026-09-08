"""Optimistic decisions with per-group conflict detection."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        if group not in decision_store.rows or actor not in decision_store.rows[group]:
            return None

        row = decision_store.rows[group]
        # A decision may only remove an active actor when another actor keeps
        # this group valid.  The revision makes the decision conditional on
        # precisely the state it observed.
        if not row[actor] or not any(active for other, active in row.items()
                                    if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        try:
            group, actor, revision = value
        except (TypeError, ValueError):
            return 'conflict'

        if (group not in decision_store.rows
                or actor not in decision_store.rows[group]
                or decision_store.revisions[group] != revision):
            return 'conflict'

        row = decision_store.rows[group]
        # Recheck the invariant as a defence in depth measure.  A token from
        # an older state cannot pass the revision test, and this also keeps
        # commits safe if a store is changed outside this service.
        if not row[actor] or not any(active for other, active in row.items()
                                    if other != actor):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
