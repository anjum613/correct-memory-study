def run(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    if operation == 'check':
        if store.approximate:
            return store.preliminary(item)
        return item in store.grants or store.preliminary(item)
    return False
