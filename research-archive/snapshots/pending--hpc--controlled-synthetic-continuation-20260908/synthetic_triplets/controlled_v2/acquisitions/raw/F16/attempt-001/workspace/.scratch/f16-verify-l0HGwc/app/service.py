def get_child(parent, store, child_id=None):
    if child_id is None:
        child_id = parent.child_ids[0]
    child = store.get(child_id)
    if child.parent_id != parent.parent_id:
        raise ValueError("child does not belong to parent")
    return child
