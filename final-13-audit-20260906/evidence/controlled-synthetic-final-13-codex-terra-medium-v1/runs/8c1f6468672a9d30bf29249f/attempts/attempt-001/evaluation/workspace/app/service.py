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

    # A negative prefilter result is definitive enough to avoid a storage read,
    # but a positive result must be confirmed against the authoritative page.
    if not store.preliminary(item):
        return False
    if item in store.read_page(store.page_for(item)):
        store.grants.append(item)
        return True
    return False
