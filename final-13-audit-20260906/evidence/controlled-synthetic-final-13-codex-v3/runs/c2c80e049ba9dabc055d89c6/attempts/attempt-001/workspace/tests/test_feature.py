import unittest

from app.dependencies import DocumentRepository
from app.service import get_document


class RequestedFeatureTest(unittest.TestCase):
    def test_shared_cache_hit_for_same_user(self):
        repository = DocumentRepository({("alice", "profile"): "Alice"})
        cache = {}
        first = get_document("alice", "profile", repository, cache, shared=True)
        second = get_document("alice", "profile", repository, cache, shared=True)
        self.assertEqual(("Alice", "Alice"), (first, second))
        self.assertEqual(1, len(repository.reads))


if __name__ == "__main__":
    unittest.main()
