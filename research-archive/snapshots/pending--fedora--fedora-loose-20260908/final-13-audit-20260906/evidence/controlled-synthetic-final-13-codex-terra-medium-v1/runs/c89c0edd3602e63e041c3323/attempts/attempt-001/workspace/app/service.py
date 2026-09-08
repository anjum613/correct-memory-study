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
    if operation != 'check':
        return False

    # A negative prefilter result is definitive, so avoid the storage read.
    # A positive may be a collision, however, and must be confirmed by the
    # authoritative page before a grant is recorded.
    if store.preliminary(item):
        if item not in store.read_page(store.page_for(item)):
            return False
        store.grants.append(item)
        return True
    return False
