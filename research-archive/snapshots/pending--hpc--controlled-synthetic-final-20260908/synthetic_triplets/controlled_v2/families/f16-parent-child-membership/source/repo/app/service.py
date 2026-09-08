def get_selected_child(parent, index: int, store):
    child_id = parent.child_ids[index]
    return store.get(child_id)
