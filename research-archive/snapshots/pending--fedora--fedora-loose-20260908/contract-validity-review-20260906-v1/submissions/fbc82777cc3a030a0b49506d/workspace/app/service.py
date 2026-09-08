def _x28_update(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    return None


def run(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    
    # For 'check' operations
    if operation != 'check':
        return False
        
    # Non-approximate store: exact membership check
    if not store.approximate:
        return store.preliminary(item)
    
    # Approximate store: use prefilter's negative fast path and exact grant semantics
    if not store.preliminary(item):
        # Negative fast path: no page reads needed
        return False
    else:
        # Positive result: check if explicitly granted
        if item in store.grants:
            return True
        # If not in grants, add it to grants (exact grant semantics)
        store.grants.append(item)
        return True
