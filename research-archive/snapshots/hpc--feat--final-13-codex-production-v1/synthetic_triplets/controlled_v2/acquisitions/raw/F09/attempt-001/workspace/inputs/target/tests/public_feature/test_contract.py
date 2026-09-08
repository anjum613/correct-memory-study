import unittest

from app.dependencies import DeterministicScheduler, Registry
from app.service import reserve_batch


class RequestedFeatureTest(unittest.TestCase):
    def test_unique_batch_reservations(self):
        registry = Registry()
        results = reserve_batch(
            [("api", "alice"), ("worker", "bob")],
            registry,
            DeterministicScheduler(),
        )
        self.assertEqual(["api", "worker"], [item.name for item in results])
        self.assertEqual({"api": "alice", "worker": "bob"}, registry.claims)


if __name__ == "__main__":
    unittest.main()
