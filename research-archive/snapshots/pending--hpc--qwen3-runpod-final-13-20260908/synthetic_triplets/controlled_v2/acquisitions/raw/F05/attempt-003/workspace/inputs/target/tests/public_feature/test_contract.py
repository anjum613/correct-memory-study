import unittest

from app.dependencies import AliasResolver, AssetStore, Cart
from app.models import Asset
from app.service import fetch_asset


class RequestedFeatureTest(unittest.TestCase):
    def test_alias_selects_owned_asset(self):
        first = Asset("a1", "alice", "photo")
        second = Asset("a2", "alice", "invoice")
        result = fetch_asset(
            Cart("alice", ["a1"]),
            AssetStore([first, second]),
            AliasResolver({"invoice": "a2"}),
            alias="invoice",
        )
        self.assertEqual(second, result)


if __name__ == "__main__":
    unittest.main()
