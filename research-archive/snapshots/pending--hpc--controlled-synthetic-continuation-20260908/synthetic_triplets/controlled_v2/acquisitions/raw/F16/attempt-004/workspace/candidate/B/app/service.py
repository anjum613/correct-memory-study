def get_child(parent, store, child_id=None):
    if child_id is not None:
        raise NotImplementedError("direct child selection is not implemented")

    return store.get(parent.child_ids[0])
