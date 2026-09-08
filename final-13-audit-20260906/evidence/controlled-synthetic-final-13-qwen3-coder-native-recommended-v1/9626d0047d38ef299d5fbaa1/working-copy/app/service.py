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
    # For check operations, we need to distinguish between approximate and non-approximate stores
    if operation == 'check':
        if not store.approximate:
            # Non-approximate: exact semantics
            return store.preliminary(item)
        else:
            # Approximate: check grants first (fast path), then prefilter
            if item in store.grants:
                return True
            # Negative fast path: if prefilter says no, return quickly
            if not store.preliminary(item):
                return False
            # Positive result: add to grants for future fast path
            store.grants.append(item)
            return True
    return False
