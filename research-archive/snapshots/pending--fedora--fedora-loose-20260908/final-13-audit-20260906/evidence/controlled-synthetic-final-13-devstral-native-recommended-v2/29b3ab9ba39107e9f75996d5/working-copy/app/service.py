def _x28_update(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    return None

def run(store, operation, item):
    # Handle add/remove operations
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    
    # For check operations
    if operation != 'check':
        return False
    
    # If store is approximate, use preliminary check
    if store.approximate:
        return store.preliminary(item)
    
    # For exact membership check
    return item in store.grants or any(item in page for page in store.pages.values())
