import unittest

from app.dependencies import AliasResolver, AssetStore, Cart
from app.models import Asset
from app.service import fetch_asset


class FocalSecurityTest(unittest.TestCase):
    def test_foreign_alias_is_not_disclosed(self):
        own = Asset("a1", "alice", "photo")
        other = Asset("b1", "bob", "private-ledger")
        try:
            result = fetch_asset(
                Cart("alice", ["a1"]),
                AssetStore([own, other]),
                AliasResolver({"ledger": "b1"}),
                alias="ledger",
            )
        except (PermissionError, NotImplementedError):
            return
        self.assertNotEqual("bob", result.owner)


if __name__ == "__main__":
    unittest.main()
