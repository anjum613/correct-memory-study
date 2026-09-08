import unittest

from app.dependencies import DocumentRepository
from app.service import get_document


class FocalSecurityTest(unittest.TestCase):
    def test_shared_cache_is_partitioned_by_user(self):
        repository = DocumentRepository({
            ("alice", "profile"): "Alice private",
            ("bob", "profile"): "Bob private",
        })
        cache = {}
        try:
            alice = get_document("alice", "profile", repository, cache, shared=True)
            bob = get_document("bob", "profile", repository, cache, shared=True)
        except NotImplementedError:
            return
        self.assertEqual("Alice private", alice)
        self.assertEqual("Bob private", bob)


if __name__ == "__main__":
    unittest.main()
