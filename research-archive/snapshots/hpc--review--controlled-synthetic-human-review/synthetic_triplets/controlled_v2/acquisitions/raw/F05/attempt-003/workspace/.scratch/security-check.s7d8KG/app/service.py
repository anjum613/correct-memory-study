def fetch_asset(cart, store, resolver, alias=None):
    if alias is not None:
        asset_id = resolver.resolve(alias)
    else:
        asset_id = cart.selected(0)

    asset = store.get(asset_id)
    if asset.owner != cart.owner:
        raise PermissionError("asset does not belong to cart owner")
    return asset
