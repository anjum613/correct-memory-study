"""Concurrent decision implementation supporting multi-record invariants."""

import copy

# Global state to track active prepares
_active_prepares = {}


def run(decision_store, operation, value):
    if operation == "read":
        return copy.deepcopy(decision_store.rows[value])
    
    if operation == "prepare":
        group, actor = value
        # Check if the actor is active and there's at least one other active actor
        if group not in decision_store.rows or actor not in decision_store.rows[group] or (not decision_store.rows[group][actor]):
            return None
        
        # Check if there's at least one other active actor in the same group
        if not any((active for other, active in decision_store.rows[group].items() if other != actor)):
            return None
        
        # Create a prepare token with revision info
        prepare_token = (group, actor, decision_store.revisions[group])
        
        # Store the prepare for potential commit
        _active_prepares[prepare_token] = decision_store
        
        return prepare_token
    
    if operation == "commit":
        # value should be a prepare token
        if value not in _active_prepares:
            return "conflict"
        
        # Verify the revision hasn't changed
        group, actor, revision = value
        if decision_store.revisions[group] != revision:
            return "conflict"
        
        # Apply the commit
        decision_store.commit(group, actor)
        
        # Clean up the prepare
        del _active_prepares[value]
        
        return "committed"
    
    raise ValueError(operation)
