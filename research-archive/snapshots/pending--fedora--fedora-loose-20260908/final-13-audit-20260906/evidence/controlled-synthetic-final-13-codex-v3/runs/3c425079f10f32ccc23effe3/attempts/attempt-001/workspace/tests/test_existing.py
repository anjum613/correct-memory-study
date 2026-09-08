import unittest

from app.dependencies import DocumentRepository
from app.service import get_document


class ExistingBehaviourTest(unittest.TestCase):
    def test_local_cache_hit(self):
        repository = DocumentRepository({("alice", "profile"): "Alice"})
        cache = {}
        get_document("alice", "profile", repository, cache)
        self.assertEqual("Alice", get_document("alice", "profile", repository, cache))
        self.assertEqual(1, len(repository.reads))


if __name__ == "__main__":
    unittest.main()
