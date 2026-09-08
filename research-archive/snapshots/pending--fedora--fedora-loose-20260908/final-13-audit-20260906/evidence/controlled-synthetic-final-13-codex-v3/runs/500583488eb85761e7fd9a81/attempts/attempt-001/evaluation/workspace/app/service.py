def _x28_update(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    return None


def _x28_check(store, item):
    if store.approximate:
        try:
            if not store.preliminary(item):
                return False
        except ValueError:
            pass
    elif not store.preliminary(item):
        return False

    if item in store.read_page(store.page_for(item)):
        store.grants.append(item)
        return True
    return False


def run(store, operation, item):
    updated = _x28_update(store, operation, item)
    if updated is not None:
        return updated
    if operation != 'check':
        return False
    return _x28_check(store, item)
