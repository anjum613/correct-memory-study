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
    if operation != 'check' or not store.preliminary(item):
        return False
    try:
        records = store.read_page(store.page_for(item))
    except OSError:
        return False
    if item not in records:
        return False
    store.grants.append(item)
    return True
