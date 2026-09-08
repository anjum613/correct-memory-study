def run(store, operation, item):
    if operation == 'add':
        store.insert(item)
        return True
    if operation == 'remove':
        store.remove(item)
        return True
    if operation == 'check':
        if store.approximate:
            # For approximate stores, use the preliminary check
            # which is the negative fast path
            return store.preliminary(item)
        else:
            # For exact stores, check the actual store
            page = store.page_for(item)
            if item in store.pages.get(page, set()):
                # If found, add to grants and return True
                store.grants.append(item)
                return True
            # If not found and not in grants, return False
            return item not in store.grants
    return False
