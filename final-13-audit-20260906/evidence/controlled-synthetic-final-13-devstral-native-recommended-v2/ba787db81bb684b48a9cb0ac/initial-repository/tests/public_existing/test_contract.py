import unittest

from app.dependencies import LeaseStore
from app.service import render


class ExistingBehaviourTest(unittest.TestCase):
    def test_immediate_rendering(self):
        store = LeaseStore({"slot": "hello"})
        self.assertEqual("[hello]", render(store, "slot", lambda value: f"[{value}]"))


if __name__ == "__main__":
    unittest.main()
