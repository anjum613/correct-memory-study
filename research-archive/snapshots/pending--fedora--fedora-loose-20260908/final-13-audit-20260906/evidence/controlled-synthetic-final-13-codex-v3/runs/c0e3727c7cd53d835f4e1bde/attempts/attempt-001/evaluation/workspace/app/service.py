import copy


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])

    if operation == 'prepare':
        try:
            group, actor = value
        except (TypeError, ValueError):
            return None

        if (
            group not in decision_store.rows
            or actor not in decision_store.rows[group]
            or not decision_store.rows[group][actor]
        ):
            return None
        if not any(
            active for other, active in decision_store.rows[group].items() if other != actor
        ):
            return None
        return (group, actor, decision_store.revisions[group])

    if operation == 'commit':
        try:
            group, actor, revision = value
        except (TypeError, ValueError):
            return 'conflict'

        if (
            group not in decision_store.rows
            or actor not in decision_store.rows[group]
            or revision != decision_store.revisions[group]
            or not decision_store.rows[group][actor]
        ):
            return 'conflict'

        decision_store.commit(group, actor)
        return 'committed'

    raise ValueError(operation)
