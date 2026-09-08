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
    
    # For check operations on approximate stores
    if operation == 'check' and store.approximate:
        # Use prefilter negative fast path: if item definitely not in store, return False
        if not store.preliminary(item):
            return False
        # If prefilter indicates item MIGHT be in store, check authoritative store
        # and potentially grant it
        if item in store.pages.get(store.page_for(item), set()):
            store.grants.append(item)
            return True
        return False
    
    # For check operations on non-approximate stores, do exact check
    if operation == 'check' and not store.approximate:
        return store.preliminary(item)
    
    # Default behavior for non-check operations or when store is approximate
    return False
