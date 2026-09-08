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
    
    # Handle check operation
    if operation != 'check':
        return False
    
    # For non-approximate stores, use exact membership check
    if not store.approximate:
        return item in store.grants or any(item in page for page in store.pages.values())
    
    # For approximate stores, use the preliminary check
    if store.preliminary(item):
        store.grants.append(item)
        return True
    
    return False
