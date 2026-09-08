def get_child(parent, store):
    child_id = parent.child_ids[0]
    return store.get(child_id)
