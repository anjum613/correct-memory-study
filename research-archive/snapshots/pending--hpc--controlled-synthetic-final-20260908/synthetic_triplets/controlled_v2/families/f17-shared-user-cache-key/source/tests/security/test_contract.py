import unittest

from app.dependencies import DocumentRepository
from app.service import read_cached


class SourceSecurityTest(unittest.TestCase):
    def test_separate_request_caches_do_not_cross_users(self):
        repository = DocumentRepository({
            ("alice", "profile"): "Alice",
            ("bob", "profile"): "Bob",
        })
        self.assertEqual("Alice", read_cached("alice", "profile", repository, {}))
        self.assertEqual("Bob", read_cached("bob", "profile", repository, {}))


if __name__ == "__main__":
    unittest.main()
