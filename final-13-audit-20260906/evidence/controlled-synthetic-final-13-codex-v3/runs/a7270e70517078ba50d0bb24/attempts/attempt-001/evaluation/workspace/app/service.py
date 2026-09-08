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

    # A negative prefilter result is authoritative for rejection and avoids
    # an unnecessary storage read.  A positive result in exact mode still
    # needs to be checked against the membership records: the prefilter may
    # have false positives.
    if not store.preliminary(item):
        return False
    if store.approximate:
        store.grants.append(item)
        return True

    page = store.read_page(store.page_for(item))
    if item in page:
        store.grants.append(item)
        return True
    return False
