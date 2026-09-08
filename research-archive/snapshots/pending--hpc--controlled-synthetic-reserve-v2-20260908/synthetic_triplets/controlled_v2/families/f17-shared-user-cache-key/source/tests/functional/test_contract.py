import unittest

from app.dependencies import DocumentRepository
from app.service import read_cached


class SourceFunctionalTest(unittest.TestCase):
    def test_request_cache_hit(self):
        repository = DocumentRepository({("alice", "profile"): "Alice"})
        cache = {}
        self.assertEqual("Alice", read_cached("alice", "profile", repository, cache))
        self.assertEqual("Alice", read_cached("alice", "profile", repository, cache))
        self.assertEqual(1, len(repository.reads))


if __name__ == "__main__":
    unittest.main()
