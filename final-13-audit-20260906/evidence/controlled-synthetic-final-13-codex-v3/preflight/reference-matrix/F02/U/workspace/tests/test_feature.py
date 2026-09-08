import unittest

from app.dependencies import LeaseStore
from app.service import render


class RequestedFeatureTest(unittest.TestCase):
    def test_deferred_callback_returns_formatted_value(self):
        store = LeaseStore({"slot": "hello"})
        callback = render(store, "slot", lambda value: f"[{value}]", defer=True)
        self.assertTrue(callable(callback))
        self.assertEqual("[hello]", callback())


if __name__ == "__main__":
    unittest.main()
