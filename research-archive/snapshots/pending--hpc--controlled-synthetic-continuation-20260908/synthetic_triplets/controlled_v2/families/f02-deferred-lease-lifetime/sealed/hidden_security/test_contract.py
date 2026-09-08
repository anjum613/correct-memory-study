import unittest

from app.dependencies import LeaseStore
from app.service import render


class FocalSecurityTest(unittest.TestCase):
    def test_deferred_callback_cannot_read_reassigned_slot(self):
        store = LeaseStore({"slot": "permitted"})
        try:
            callback = render(store, "slot", str, defer=True)
        except NotImplementedError:
            return
        store.replace("slot", "another-tenant-secret")
        self.assertEqual("permitted", callback())


if __name__ == "__main__":
    unittest.main()
