"""Read-only baseline for concurrent decisions."""

import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    if operation == 'prepare':
        try:
            group, actor = value
            row = decision_store.rows[group]
            revision = decision_store.revisions[group]
        except (KeyError, TypeError, ValueError):
            return None

        # A decision can only be prepared while it has a companion active
        # decision in its record.  Keep the revision in the token so that a
        # retry for the same record cannot accidentally commit an old read.
        if actor not in row or not row[actor]:
            return None
        if not any(active for other, active in row.items() if other != actor):
            return None
        return (group, actor, revision)
    if operation == 'commit':
        try:
            group, actor, revision = value
            row = decision_store.rows[group]
            if decision_store.revisions[group] != revision:
                return 'conflict'
            if actor not in row or not row[actor]:
                return 'conflict'

            # Validate the whole invariant against the prospective state.
            # This permits independent records to commit from the same
            # snapshot, while still rejecting the operation that would make
            # any record empty.
            valid = all(
                any(
                    active if current_group != group or other != actor else False
                    for other, active in record.items()
                )
                for current_group, record in decision_store.rows.items()
            )
            if not valid:
                return 'conflict'

            decision_store.commit(group, actor)
            return 'committed'
        except (KeyError, TypeError, ValueError):
            return 'conflict'
    raise ValueError(operation)
