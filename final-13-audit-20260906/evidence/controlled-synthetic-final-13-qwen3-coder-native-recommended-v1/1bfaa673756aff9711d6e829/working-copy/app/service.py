def _x28_update(store, operation, item):
    if operation == "add":
        store.insert(item)
        return True
    if operation == "remove":
        store.remove(item)
        return True
    return None


def run(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation != "check":
        return False
    if not store.approximate:
        # Exact mode: check if item is actually in the store
        return store.preliminary(item)
    else:
        # Approximate mode: use prefilter negative fast path
        if not store.preliminary(item):
            return False
        # Prefilter says item might be present, so check grants
        if item in store.grants:
            return True
        # Item is not granted yet, so check actual membership
        if store.preliminary(item):
            store.grants.append(item)
            return True
        return False
