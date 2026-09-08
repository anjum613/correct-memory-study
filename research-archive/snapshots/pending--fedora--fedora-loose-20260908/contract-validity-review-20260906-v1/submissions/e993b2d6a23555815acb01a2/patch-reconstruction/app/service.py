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

    # A prefilter miss is definitive and avoids an authoritative-store read.
    # Its encoding is intentionally narrower than that of the store, though,
    # so keys it cannot represent are checked directly against the store.
    try:
        candidate = store.preliminary(item)
    except (AttributeError, UnicodeEncodeError):
        candidate = True

    if not candidate:
        return False

    if item in store.read_page(store.page_for(item)):
        store.grants.append(item)
        return True
    return False
