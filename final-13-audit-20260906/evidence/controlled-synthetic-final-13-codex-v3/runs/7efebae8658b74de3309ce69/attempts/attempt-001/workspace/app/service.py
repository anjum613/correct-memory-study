def run(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    if operation != 'check':
        return False

    if store.approximate and not store.preliminary(item):
        return False

    for entry in store.read_page(store.page_for(item)):
        if entry == item:
            store.grants.append(item)
            return True
    return False
