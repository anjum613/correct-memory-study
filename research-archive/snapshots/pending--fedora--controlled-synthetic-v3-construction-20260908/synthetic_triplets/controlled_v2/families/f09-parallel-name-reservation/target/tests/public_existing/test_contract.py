import unittest

from app.dependencies import Registry
from app.service import reserve_one


class ExistingBehaviourTest(unittest.TestCase):
    def test_single_reservation(self):
        registry = Registry()
        result = reserve_one("api", "alice", registry)
        self.assertEqual("alice", registry.claims[result.name])


if __name__ == "__main__":
    unittest.main()
