"""Concurrent decision handler."""

import copy


# Global state to track ongoing operations
ongoing_operations = {}


def run(decision_store, operation, value):
    if operation == 'read':
        return copy.deepcopy(decision_store.rows[value])
    
    elif operation == 'prepare':
        group, actor = value
        # Check if we can prepare this operation
        if group not in decision_store.rows or actor not in decision_store.rows[group]:
            return None
            
        # Check if the actor is already disabled
        if not decision_store.rows[group][actor]:
            return None
            
        # Check if there are other active actors (multi-record invariant)
        active_actors = [k for k, v in decision_store.rows[group].items() if v]
        if len(active_actors) <= 1:
            return None
            
        # Create a snapshot of the current state for this operation
        snapshot = {
            'group': group,
            'actor': actor,
            'revision': decision_store.revisions[group]
        }
        
        # Store this operation for potential conflict checking
        operation_id = id(snapshot)  # Simple way to identify this operation
        ongoing_operations[operation_id] = snapshot
        
        return operation_id
    
    elif operation == 'commit':
        # Check if this is a valid operation ID
        if value not in ongoing_operations:
            return 'conflict'
            
        operation_info = ongoing_operations[value]
        group = operation_info['group']
        actor = operation_info['actor']
        expected_revision = operation_info['revision']
        
        # Check if the revision has changed (indicating conflict)
        if decision_store.revisions[group] != expected_revision:
            return 'conflict'
            
        # Check if the actor is still active (in case another committed first)
        if not decision_store.rows[group][actor]:
            return 'conflict'
            
        # Perform the actual commit
        decision_store.rows[group][actor] = False
        decision_store.revisions[group] += 1
        decision_store.events.append(('commit', group, actor))
        
        # Clean up the operation
        del ongoing_operations[value]
        
        return 'committed'
    
    raise ValueError(f"Unknown operation: {operation}")
