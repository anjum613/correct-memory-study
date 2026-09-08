class Cart:
    def __init__(self, owner, asset_ids):
        self.owner = owner
        self._asset_ids = tuple(asset_ids)

    def selected(self, index):
        return self._asset_ids[index]


class AliasResolver:
    def __init__(self, aliases):
        self.aliases = dict(aliases)

    def resolve(self, alias):
        return self.aliases[alias]


class AssetStore:
    def __init__(self, assets):
        self.assets = {asset.asset_id: asset for asset in assets}

    def get(self, asset_id):
        return self.assets[asset_id]
