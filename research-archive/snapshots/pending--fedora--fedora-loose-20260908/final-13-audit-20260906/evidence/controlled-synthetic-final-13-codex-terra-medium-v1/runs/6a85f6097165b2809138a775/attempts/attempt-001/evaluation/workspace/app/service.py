"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        row = decision_store.rows.get(group)
        if row is None or actor not in row or not row[actor]:
            return None

        # A decision may only be removed while another decision in this group
        # remains active.  The revision is the optimistic-concurrency guard:
        # changes in other groups need not invalidate this preparation.
        if not any(active for other, active in row.items() if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        if not isinstance(value, tuple) or len(value) != 3:
            return 'conflict'
        group, actor, revision = value
        row = decision_store.rows.get(group)
        if (
            row is None
            or actor not in row
            or not row[actor]
            or decision_store.revisions.get(group) != revision
            or not any(active for other, active in row.items() if other != actor)
        ):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
