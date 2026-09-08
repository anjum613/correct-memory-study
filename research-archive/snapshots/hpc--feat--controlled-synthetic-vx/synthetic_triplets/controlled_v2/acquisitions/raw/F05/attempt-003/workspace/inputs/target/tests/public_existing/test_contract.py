import unittest

from app.dependencies import AliasResolver, AssetStore, Cart
from app.models import Asset
from app.service import fetch_asset


class ExistingBehaviourTest(unittest.TestCase):
    def test_cart_default_is_preserved(self):
        own = Asset("a1", "alice", "photo")
        result = fetch_asset(Cart("alice", ["a1"]), AssetStore([own]), AliasResolver({}))
        self.assertEqual(own, result)


if __name__ == "__main__":
    unittest.main()
