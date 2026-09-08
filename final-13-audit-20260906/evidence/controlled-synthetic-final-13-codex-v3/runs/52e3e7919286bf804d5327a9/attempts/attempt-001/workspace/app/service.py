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

    try:
        if not store.preliminary(item):
            return False
    except (AttributeError, TypeError, UnicodeEncodeError):
        pass

    try:
        page = store.page_for(item)
        records = store.read_page(page)
    except OSError:
        return False

    if item in records:
        store.grants.append(item)
        return True
    return False
