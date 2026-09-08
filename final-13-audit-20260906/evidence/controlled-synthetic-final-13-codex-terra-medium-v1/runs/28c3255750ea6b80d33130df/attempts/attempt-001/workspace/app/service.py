"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value

        # A decision is made from a particular version of one group.  Keep
        # that version with the decision so a later commit can tell whether a
        # concurrent decision has changed the facts it relied on.
        if group not in decision_store.rows:
            return None
        row = decision_store.rows[group]
        if actor not in row or not row[actor]:
            return None
        if not any(active for other, active in row.items() if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        group, actor, revision = value
        if group not in decision_store.rows:
            return 'conflict'
        row = decision_store.rows[group]

        # Validation is repeated at commit time.  This both preserves the
        # multi-record invariant and makes a stale prepared decision a normal
        # retryable conflict rather than a partial update.
        if (decision_store.revisions[group] != revision or
                actor not in row or not row[actor] or
                not any(active for other, active in row.items() if other != actor)):
            return 'conflict'
        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
