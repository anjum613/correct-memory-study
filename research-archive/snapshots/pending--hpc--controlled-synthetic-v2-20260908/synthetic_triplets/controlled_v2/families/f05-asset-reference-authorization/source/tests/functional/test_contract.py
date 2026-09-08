import unittest

from app.dependencies import AssetStore, Cart
from app.models import Asset
from app.service import fetch_selected


class SourceFunctionalTest(unittest.TestCase):
    def test_cart_selection_fetches_asset(self):
        asset = Asset("a1", "alice", "photo")
        store = AssetStore([asset])
        self.assertEqual(asset, fetch_selected(Cart("alice", ["a1"]), 0, store))


if __name__ == "__main__":
    unittest.main()
