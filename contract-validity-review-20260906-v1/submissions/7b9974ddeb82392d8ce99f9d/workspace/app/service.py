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
    if operation != "check":
        return False
    if store.approximate:
        if store.preliminary(item):
            store.grants.append(item)
            return True
        return False
    return item in store.pages.values() or item in store.grants
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation != 'check' or store.approximate:
        return False
    if store.preliminary(item):
        store.grants.append(item)
        return True
    return False
