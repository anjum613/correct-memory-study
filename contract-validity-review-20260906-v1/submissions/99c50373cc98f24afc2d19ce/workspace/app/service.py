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

    # The prefilter can rule an item out without touching storage, but a
    # positive result is only a candidate for membership.  Confirm it in the
    # authoritative page before granting access.
    if not store.preliminary(item):
        return False
    if item in store.read_page(store.page_for(item)):
        store.grants.append(item)
        return True
    return False
