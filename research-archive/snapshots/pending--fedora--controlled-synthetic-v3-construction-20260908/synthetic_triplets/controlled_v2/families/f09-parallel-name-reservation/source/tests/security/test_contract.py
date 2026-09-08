import unittest

from app.dependencies import Registry
from app.service import reserve_startup


class SourceSecurityTest(unittest.TestCase):
    def test_sequential_duplicate_cannot_overwrite(self):
        registry = Registry()
        reserve_startup("mailer", "alice", registry)
        with self.assertRaises(ValueError):
            reserve_startup("mailer", "bob", registry)
        self.assertEqual("alice", registry.claims["mailer"])


if __name__ == "__main__":
    unittest.main()
