import unittest

from app.dependencies import LeaseStore
from app.service import render_now


class SourceFunctionalTest(unittest.TestCase):
    def test_formats_inside_lease(self):
        store = LeaseStore({"daily": "ready"})
        self.assertEqual("<ready>", render_now(store, "daily", lambda value: f"<{value}>"))


if __name__ == "__main__":
    unittest.main()
