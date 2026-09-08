"""Concurrent decision service implementation."""

import copy


def run(decision_store, operation, value):
    if operation == "read":
        return copy.deepcopy(decision_store.rows[value])
    if operation == "prepare":
        group, actor = value
        # Check if actor is eligible for this group
        if group not in decision_store.rows or actor not in decision_store.rows[group] or (not decision_store.rows[group][actor]):
            return None
        # Check if there are other active actors in this group
        if not any((active for other, active in decision_store.rows[group].items() if other != actor)):
            return None
        # Return the prepare token
        return (group, actor, decision_store.revisions[group])
    if operation == "commit":
        group, actor, revision = value
        # Validate the commit
        if decision_store.revisions[group] != revision:
            return "conflict"
        # Perform the actual commit
        decision_store.commit(group, actor)
        return "committed"
    raise ValueError(operation)
