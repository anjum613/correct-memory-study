import unittest

from app.dependencies import LeaseStore
from app.service import render_now


class SourceSecurityTest(unittest.TestCase):
    def test_completed_result_cannot_follow_slot_reuse(self):
        store = LeaseStore({"slot": "permitted"})
        rendered = render_now(store, "slot", str.upper)
        store.replace("slot", "another-tenant-secret")
        self.assertEqual("PERMITTED", rendered)


if __name__ == "__main__":
    unittest.main()
