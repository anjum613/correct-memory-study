import unittest

from app.dependencies import AssetStore, Cart
from app.models import Asset
from app.service import fetch_selected


class SourceSecurityTest(unittest.TestCase):
    def test_cart_exposes_only_server_bound_ids(self):
        own = Asset("a1", "alice", "photo")
        other = Asset("b1", "bob", "private")
        store = AssetStore([own, other])
        cart = Cart("alice", ["a1"])
        self.assertEqual("alice", fetch_selected(cart, 0, store).owner)
        with self.assertRaises(IndexError):
            fetch_selected(cart, 1, store)


if __name__ == "__main__":
    unittest.main()
