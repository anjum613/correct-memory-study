def fetch_asset(cart, store, resolver, alias=None):
    if alias is not None:
        raise NotImplementedError("alias-based asset selection is not implemented")

    asset_id = cart.selected(0)
    return store.get(asset_id)
