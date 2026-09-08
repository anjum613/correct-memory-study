def fetch_selected(cart, index: int, store):
    asset_id = cart.selected(index)
    return store.get(asset_id)
