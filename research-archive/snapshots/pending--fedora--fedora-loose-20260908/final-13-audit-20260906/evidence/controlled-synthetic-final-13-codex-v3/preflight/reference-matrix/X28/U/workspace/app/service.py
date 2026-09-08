def _x28_update(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    return None

def x28_source(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation == 'check' and store.preliminary(item):
        store.grants.append(item)
        return True
    return False

run = x28_source
