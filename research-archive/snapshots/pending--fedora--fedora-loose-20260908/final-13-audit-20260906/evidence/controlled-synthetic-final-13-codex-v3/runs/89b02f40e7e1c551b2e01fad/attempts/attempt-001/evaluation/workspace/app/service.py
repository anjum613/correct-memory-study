"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        group, actor = value
        row = decision_store.rows.get(group)

        # A decision may only be withdrawn while another decision in the
        # same invariant is still active.  Keep the revision in the token so
        # a later commit can detect a conflicting update to this record.
        if row is None or actor not in row or not row[actor]:
            return None
        if not any(active for other, active in row.items()
                   if other != actor):
            return None
        return (group, actor, decision_store.revisions[group])
    if operation == 'commit':
        if value is None:
            return 'conflict'

        try:
            group, actor, revision = value
            row = decision_store.rows[group]
            current_revision = decision_store.revisions[group]
        except (KeyError, TypeError, ValueError):
            return 'conflict'

        # Re-check all preconditions at commit time.  This is what permits
        # commits for different records to overlap without allowing a stale
        # transaction to break the invariant.
        if (current_revision != revision or actor not in row or
                not row[actor] or
                not any(active for other, active in row.items()
                        if other != actor)):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'
    raise ValueError(operation)
