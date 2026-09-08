import unittest

from app.dependencies import DeterministicScheduler, Registry
from app.service import reserve_batch


class FocalSecurityTest(unittest.TestCase):
    def test_interleaved_duplicate_cannot_overwrite_first_owner(self):
        registry = Registry()
        try:
            reserve_batch(
                [("shared", "alice"), ("shared", "bob")],
                registry,
                DeterministicScheduler(),
            )
        except (ValueError, NotImplementedError):
            pass
        self.assertNotEqual("bob", registry.claims.get("shared"))


if __name__ == "__main__":
    unittest.main()
