import unittest
from app import service as s
from app import runtime as r

class Existing(unittest.TestCase):
    def test_local_hit(self):
        repo, cache = r.Repository({('a', 'doc'): ''}), {}
        self.assertEqual('', s.get_one('a', 'doc', repo, cache))
        self.assertEqual('', s.get_one('a', 'doc', repo, cache))
        self.assertEqual([('a', 'doc')], repo.reads)

if __name__ == '__main__':
    unittest.main(verbosity=2)
