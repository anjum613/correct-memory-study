def fetch_asset(cart, store, resolver):
    asset_id = cart.selected(0)
    return store.get(asset_id)
