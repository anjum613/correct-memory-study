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
    # A negative prefilter result is conclusive, but a positive result is
    # only a candidate: the page is the authoritative membership store.
    if not store.preliminary(item):
        return False
    if item in store.read_page(store.page_for(item)):
        store.grants.append(item)
        return True
    return False
